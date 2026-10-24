"""Offline Storage semantics, not a replacement ledger implementation."""

from copy import deepcopy
import threading
import time

from cloud_control import Conflict, ControlError, RequestBudget, encoded, initial_state
from protocol import digest

BINDING = {
    "schema": "azure-table-control-v1", "experiment": "master-openai-instability",
    "storage_resource_id": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/fixture/providers/Microsoft.Storage/storageAccounts/fixture",
    "table": "Fixture", "container": "fixture", "authority_id": "00000000-0000-0000-0000-000000000001",
    "resource_id": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/fixture/providers/Microsoft.CognitiveServices/accounts/fixture",
    "endpoint": "https://fixture.openai.azure.com",
}
PLAN = {
    "max_requests": 100000100, "session_requests": 1000000, "max_sessions": 100,
    "session_seconds": 14400, "request_usd": "0.00000000001", "margin": "1.25",
    "bootstrap_usd": ".001", "capacity_usd": ".001", "transfer_usd": ".001", "reserve_usd": ".01",
    "evidence": "synthetic offline rates only", "retention_until": "2099-01-01T00:00:00Z",
}


class MemoryStorage:
    def __init__(self):
        self.rows = {"root": (initial_state(BINDING, PLAN), 1)}
        self.rows["root"][0]["probe_verified"] = True
        self.lock = threading.RLock()
        self.lease = None
        self.clock = time.monotonic
        self.lease_until = 0
        self.sequence = 1
        self.after_commit = None


class FakeStore:
    def __init__(self, storage=None):
        self.storage = storage or MemoryStorage()
        self.budget = RequestBudget(PLAN["session_requests"])

    def get(self, key):
        self.budget.charge()
        with self.storage.lock:
            return deepcopy(self.storage.rows.get(key, (None, None)))

    def transaction(self, changes):
        self.budget.charge(len(changes))
        with self.storage.lock:
            if not changes or len(changes) > 100 or len({key for key, _, _ in changes}) != len(changes):
                raise ControlError("Invalid bounded control transaction.")
            for key, value, expected in changes:
                encoded(value)
                current = self.storage.rows.get(key, (None, None))[1]
                if current != expected:
                    raise Conflict("Conditional transaction conflicted.")
            for key, value, _ in changes:
                self.storage.sequence += 1
                self.storage.rows[key] = (deepcopy(value), str(self.storage.sequence))
            callback, self.storage.after_commit = self.storage.after_commit, None
            if callback:
                callback()

    def query(self, prefix):
        self.budget.charge()
        with self.storage.lock:
            return {key: deepcopy(value) for key, (value, _) in self.storage.rows.items()
                    if key.startswith(prefix)}

    def acquire(self):
        self.budget.charge()
        with self.storage.lock:
            if self.storage.lease and self.storage.clock() < self.storage.lease_until:
                raise Conflict("Lease already held.")
            lease = object()
            self.storage.lease = lease
            self.storage.lease_until = self.storage.clock() + 60
            return lease

    def renew(self, lease):
        self.budget.charge()
        with self.storage.lock:
            if self.storage.lease is not lease:
                raise Conflict("Lease lost.")
            self.storage.lease_until = self.storage.clock() + 60

    def release(self, lease):
        self.budget.charge()
        with self.storage.lock:
            if self.storage.lease is not lease:
                raise Conflict("Lease lost.")
            self.storage.lease = None

    def close(self):
        pass

    def verify_account(self):
        return {"storage_account_verified": True, "fixture": True}


def authority_fields():
    return {"control_schema": BINDING["schema"], "authority_sha256": digest(BINDING),
            "storage_reserve_usd": PLAN["reserve_usd"]}
