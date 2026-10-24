#!/usr/bin/env python3
"""Exercise pinned SDK clients with an in-memory HTTP transport, never Azure."""

from functools import partial
import importlib.metadata
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

from azure.core.credentials import AccessToken
from azure.core.exceptions import ServiceRequestError
from azure.core.pipeline.transport import HttpResponse, HttpTransport
from azure.data.tables import TableClient
from azure.storage.blob import BlobClient
from requests.structures import CaseInsensitiveDict

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK))
from cloud_control import AzureStore, RequestBudget
from fake_control import BINDING


class OfflineCredential:
    def get_token(self, *scopes, **kwargs):
        return AccessToken("offline-test-token", int(time.time()) + 3600)

    def close(self):
        pass


class OfflineResponse(HttpResponse):
    def __init__(self, request, status, headers, body):
        super().__init__(request, None)
        self.status_code = status
        self.headers = CaseInsensitiveDict(headers)
        self.content_type = self.headers.get("content-type")
        self.reason = "Offline fixture"
        self.payload = json.dumps(body).encode() if body is not None else b""

    def body(self):
        return self.payload


class OfflineTransport(HttpTransport):
    def __init__(self):
        self.requests, self.responses = [], []

    def open(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def sleep(self, duration):
        raise AssertionError("The SDK attempted an unexpected retry.")

    def send(self, request, **kwargs):
        if hasattr(request, "prepare_multipart_body"):
            request.prepare_multipart_body()
        self.requests.append(request)
        if not self.responses:
            raise ServiceRequestError("Intentional offline transport failure; nothing was sent.")
        return OfflineResponse(request, *self.responses.pop(0))


class InstalledSdkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.version_info[:2] != (3, 11):
            raise AssertionError("Run this acceptance check in the pinned Python 3.11 environment.")
        versions = {}
        for line in (TASK / "requirements.txt").read_text().splitlines():
            name, expected = line.split("==")
            versions[name] = importlib.metadata.version(name)
            if versions[name] != expected:
                raise AssertionError(f"{name}: expected {expected}, installed {versions[name]}")
        versions["azure-core"] = importlib.metadata.version("azure-core")
        print(json.dumps({"installed_versions": versions}, sort_keys=True))

    def setUp(self):
        self.transport = OfflineTransport()
        with patch("azure.identity.DefaultAzureCredential", return_value=OfflineCredential()), patch(
            "azure.data.tables.TableClient", side_effect=partial(TableClient, transport=self.transport)
        ), patch("azure.storage.blob.BlobClient", side_effect=partial(BlobClient, transport=self.transport)):
            self.store = AzureStore(BINDING, RequestBudget(100))
        self.addCleanup(self.store.close)

    def test_transaction_serializes_etags_and_does_not_retry_unknown_outcome(self):
        with self.assertRaises(ServiceRequestError):
            self.store.transaction([("root", {"n": 1}, "etag-before"), ("operation", {}, None)])
        self.assertEqual(len(self.transport.requests), 1)
        request = self.transport.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertTrue(request.url.split("?")[0].endswith("/$batch"))
        body = request.body.encode() if isinstance(request.body, str) else request.body
        self.assertIn(b"if-match: etag-before", body.lower())
        self.assertIn(b"PUT ", body)
        self.assertIn(b"POST ", body)
        self.assertNotIn(b"if-match: *", body.lower())

    def test_entity_response_preserves_etag(self):
        etag = 'W/"offline-etag"'
        self.transport.responses = [(200, {"content-type": "application/json", "etag": etag}, {
            "PartitionKey": BINDING["experiment"], "RowKey": "root",
            "value": '{"verified": true}', "odata.etag": etag,
        })]
        value, actual_etag = self.store.get("root")
        self.assertEqual(value, {"verified": True})
        self.assertEqual(actual_etag, etag)
        self.assertEqual(len(self.transport.requests), 1)

    def test_query_consumes_continuation_pages(self):
        first = {"PartitionKey": BINDING["experiment"], "RowKey": "run:a", "value": '{"n": 1}'}
        second = {"PartitionKey": BINDING["experiment"], "RowKey": "run:b", "value": '{"n": 2}'}
        self.transport.responses = [
            (200, {"content-type": "application/json",
                   "x-ms-continuation-nextpartitionkey": BINDING["experiment"],
                   "x-ms-continuation-nextrowkey": "run:b"}, {"value": [first]}),
            (200, {"content-type": "application/json"}, {"value": [second]}),
        ]
        self.assertEqual(self.store.query("run:"), {"run:a": {"n": 1}, "run:b": {"n": 2}})
        self.assertEqual(len(self.transport.requests), 2)

    def test_lease_acquire_renew_release_uses_the_same_id(self):
        lease_id = "00000000-0000-0000-0000-000000000002"
        headers = {"x-ms-lease-id": lease_id}
        self.transport.responses = [(201, headers, None), (200, headers, None), (200, headers, None)]
        lease = self.store.acquire()
        self.store.renew(lease)
        self.store.release(lease)
        self.assertEqual([request.headers["x-ms-lease-action"] for request in self.transport.requests],
                         ["acquire", "renew", "release"])
        for request in self.transport.requests[1:]:
            self.assertEqual(request.headers["x-ms-lease-id"], lease_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
