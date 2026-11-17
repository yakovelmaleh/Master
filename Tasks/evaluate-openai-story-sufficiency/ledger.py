"""New-run accounting on the existing authority; historical recovery stays immutable."""

from sufficiency import check_approval
from cloud_control import ControlError, Ledger, ROOT
from protocol import digest

RECOVERY_SCHEMA = "azure-table-control-inference-recovery-v1"


class SufficiencyLedger(Ledger):
    def bind(self, root, config):
        from protocol import read_json, study_id

        self.run = study_id(root)
        self.study_hash = digest(read_json(root / "study.json"))
        self.config = config

    def _root(self):
        state, etag = self.store.get(ROOT)
        if state is None or state.get("schema") != RECOVERY_SCHEMA:
            return super()._root()
        if state.get("authority") != digest(self.binding) or state.get("storage") != self.plan:
            raise ControlError("Authority or current storage approval differs.")
        review_hash = state.get("inference_recovery")
        if not isinstance(review_hash, str):
            raise ControlError("Missing historical recovery reference.")
        review, _ = self.store.get("inference-recovery:" + review_hash)
        if (review is None or digest(review) != review_hash
                or review.get("authority_sha256") != digest(self.binding)
                or digest(state.get("quarantine")) != review.get("training_quarantine_sha256")
                or (state.get("quarantine")
                    and state.get("training") != state["quarantine"]["operation"])):
            raise ControlError("Historical recovery or training quarantine changed.")
        if not getattr(self, "run", None) or self.run == review.get("run"):
            raise ControlError("Historical recovery is evidence only, not permission to reuse its run.")
        return state, etag

    def require_run(self, run):
        if run != getattr(self, "run", None):
            raise ControlError("This runner cannot write to a different or historical run.")

    def authorize(self, run, approval, estimate_value, config, evidence=None):
        self.require_run(run)
        check_approval(approval, self.study_hash, config)
        return super().authorize(run, approval, estimate_value, config, evidence)

    def _allow_operation(self, state, run, kind, request=None):
        self.require_run(run)
        allocation = self.allocation(run)
        if allocation is None or kind != "inference":
            raise ControlError("Only newly approved sufficiency inference is allowed.")
        check_approval(allocation["approval"], self.study_hash, self.config)
        return super()._allow_operation(state, run, kind, request)

    def record(self, run, name, value):
        self.require_run(run)
        return super().record(run, name, value)

    def finish(self, run, name, result, actual=None, terminal=False):
        self.require_run(run)
        return super().finish(run, name, result, actual, terminal)
