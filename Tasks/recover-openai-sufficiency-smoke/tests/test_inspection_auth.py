from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK))
import inspect_failure
from inspection_auth import InspectionStore, PreparedCredential, SCOPES, failure_reason
from cloud_control import ControlError


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.source = Mock()
        self.source.get_token.return_value = NS(token="PRIVATE-TOKEN", expires_on=3600)
        self.clock = Mock(return_value=1000)
        self.credential = PreparedCredential(self.source, self.clock)

    def test_prepare_once_then_cache_only_for_every_storage_operation(self):
        with self.assertRaises(ControlError):
            self.credential.get_token(SCOPES[0])
        self.source.get_token.assert_not_called()
        self.credential.prepare()
        self.assertEqual([call.args for call in self.source.get_token.call_args_list],
                         [(scope,) for scope in SCOPES])
        for _ in range(10):
            for scope in SCOPES:
                self.assertEqual(self.credential.get_token(scope).token, "PRIVATE-TOKEN")
        self.assertEqual(self.source.get_token.call_count, 2)
        with self.assertRaises(ControlError):
            self.credential.prepare()
        self.credential.close()
        self.source.close.assert_called_once()
        self.assertEqual(self.credential.tokens, {})

    def test_expiry_challenge_or_other_scope_never_refreshes(self):
        self.credential.prepare()
        for args, kwargs in (
            (("https://other.invalid/.default",), {}),
            ((SCOPES[0],), {"claims": "PRIVATE"}),
            ((SCOPES[0],), {"tenant_id": "different"}),
            (SCOPES, {}),
        ):
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ControlError):
                self.credential.get_token(*args, **kwargs)
        self.clock.return_value = 3480
        with self.assertRaises(ControlError):
            self.credential.get_token(SCOPES[1])
        self.assertEqual(self.source.get_token.call_count, 2)

    def test_failed_or_short_lived_authentication_does_not_leave_partial_cache(self):
        self.source.get_token.side_effect = [NS(token="PRIVATE", expires_on=3600), RuntimeError("PRIVATE")]
        with self.assertRaises(RuntimeError):
            self.credential.prepare()
        self.assertEqual(self.credential.tokens, {})
        with self.assertRaises(ControlError):
            self.credential.prepare()
        self.assertEqual(self.source.get_token.call_count, 2)
        self.source.get_token.side_effect = None
        self.source.get_token.return_value = NS(token="PRIVATE", expires_on=1300)
        other = PreparedCredential(self.source, self.clock)
        with self.assertRaisesRegex(ControlError, "lifetime"):
            other.prepare()
        self.assertEqual(other.tokens, {})

    def test_storage_clients_share_prepared_credential_with_original_transport_policy(self):
        cli, table, blob = Mock(return_value=self.source), Mock(), Mock()
        modules = {
            "azure.identity": NS(AzureCliCredential=cli),
            "azure.data.tables": NS(TableClient=table),
            "azure.storage.blob": NS(BlobClient=blob),
        }
        binding = {"experiment": "fixture", "storage_resource_id": "/accounts/fixture",
                   "table": "table", "container": "container"}
        with patch.dict(sys.modules, modules):
            store = InspectionStore(binding, inspect_failure.InspectionBudget(100))
        cli.assert_called_once_with(process_timeout=60)
        self.source.get_token.assert_not_called()
        for client, endpoint in ((table, "https://fixture.table.core.windows.net"),
                                 (blob, "https://fixture.blob.core.windows.net")):
            self.assertEqual(client.call_args.args[0], endpoint)
            self.assertIs(client.call_args.kwargs["credential"], store.credential)
            self.assertEqual(client.call_args.kwargs["retry_total"], 0)
            self.assertEqual(client.call_args.kwargs["connection_timeout"], 5)
            self.assertEqual(client.call_args.kwargs["read_timeout"], 10)
        with patch.object(store.credential, "prepare") as prepare:
            store.authenticate()
            prepare.assert_called_once()
        self.assertEqual(store.budget.used, 0)
        store.close()
        table.return_value.close.assert_called_once()
        blob.return_value.close.assert_called_once()

    def test_timeout_reason_never_includes_command_or_token_details(self):
        error = RuntimeError("PRIVATE-TOKEN")
        error.__cause__ = subprocess.TimeoutExpired(["PRIVATE-COMMAND"], 60)
        self.assertEqual(failure_reason(error), "cli_timeout")
        error.__cause__ = None
        error.__context__ = error
        self.assertEqual(failure_reason(error), "authentication_failed")


if __name__ == "__main__":
    unittest.main()
