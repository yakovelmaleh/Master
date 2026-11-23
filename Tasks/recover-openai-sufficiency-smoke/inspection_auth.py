"""Prepare bounded CLI credentials before any lease; never refresh under a lease."""

import subprocess
import time

from cloud_control import AzureStore, ControlError

SCOPES = ("https://management.azure.com/.default", "https://storage.azure.com/.default")


class PreparedCredential:
    def __init__(self, source, clock=time.time):
        self.source, self.clock = source, clock
        self.tokens = {}
        self.attempted = False

    def prepare(self):
        if self.attempted:
            raise ControlError("Authentication was already attempted; no automatic retry.")
        self.attempted = True
        tokens = {scope: self.source.get_token(scope) for scope in SCOPES}
        if any(token.expires_on <= self.clock() + 300 for token in tokens.values()):
            raise ControlError("Authentication token lifetime is too short for inspection.")
        self.tokens = tokens

    def get_token(self, *scopes, **kwargs):
        if len(scopes) != 1 or kwargs.get("claims") or kwargs.get("tenant_id"):
            raise ControlError("Unexpected token scope or challenge; do not refresh during inspection.")
        token = self.tokens.get(scopes[0])
        if token is None or token.expires_on <= self.clock() + 120:
            raise ControlError("Prepared token missing or expiring; stop without refreshing.")
        return token

    def close(self):
        self.tokens.clear()
        self.source.close()


class InspectionStore(AzureStore):
    def __init__(self, binding, budget):
        from azure.data.tables import TableClient
        from azure.identity import AzureCliCredential
        from azure.storage.blob import BlobClient

        # Keep the frozen transport's endpoints/timeouts/retry policy; change only credentials.
        self.binding, self.budget = binding, budget
        self.partition = binding["experiment"]
        account = binding["storage_resource_id"].rsplit("/", 1)[1]
        self.credential = PreparedCredential(AzureCliCredential(process_timeout=60))
        options = {"retry_total": 0, "connection_timeout": 5, "read_timeout": 10}
        self.table = TableClient(
            f"https://{account}.table.core.windows.net", binding["table"],
            credential=self.credential, **options,
        )
        self.blob = BlobClient(
            f"https://{account}.blob.core.windows.net", binding["container"], "coordinator",
            credential=self.credential, **options,
        )

    def authenticate(self):
        self.credential.prepare()


def failure_reason(error):
    seen = set()
    current = error
    for _ in range(8):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        if isinstance(current, subprocess.TimeoutExpired):
            return "cli_timeout"
        current = current.__cause__ or current.__context__
    return "authentication_failed"
