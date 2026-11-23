import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK))
import diagnostics as diag
from sufficiency import QUESTION
from protocol import write_json


def fixture():
    return {
        "choices": [{
            "message": {"content": "1", "refusal": None}, "finish_reason": "length",
            "logprobs": {"content": [{
                "token": "1", "logprob": -.2,
                "top_logprobs": [{"token": "0", "logprob": -1.7}, {"token": "1", "logprob": -.2}],
            }]},
        }],
        "usage": {"prompt_tokens": 30, "completion_tokens": 1}, "model": "fixture-model", "id": "PRIVATE-ID",
    }


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.config = {"model": "fixture-model", "seed": 7, "top_logprobs": 20}
        self.approval = {"base_deployment": "PRIVATE-DEPLOYMENT"}
        self.examples = {"entry": {"system": "PRIVATE-SYSTEM", "project": "Jira", "variant": "text"}}
        self.pair = [{"role": "system", "content": "PRIVATE-SYSTEM"}, {
            "role": "user", "content": json.dumps({
                "project": "Jira", "question": QUESTION, "original_text": "PRIVATE-STORY",
            }),
        }]
        self.events = {}
        self.constructor = patch.object(diag.SufficiencyBackend, "__init__", side_effect=AssertionError("No Azure client"))
        self.constructor.start()
        self.addCleanup(self.constructor.stop)
        sdk = patch.dict(sys.modules, {"openai": NS(
            APIConnectionError=type("APIConnectionError", (Exception,), {}),
            APIStatusError=type("APIStatusError", (Exception,), {}),
        )})
        sdk.start()
        self.addCleanup(sdk.stop)

    def run_probe(self, response=None, **kwargs):
        return diag.probe(self.config, self.approval, self.examples, self.pair,
                          lambda name, value: self.events.update({name: value}),
                          diag.object_tree(response) if response is not None else None, **kwargs)

    def test_exact_arguments_and_unchanged_scoring(self):
        import backend
        real_score = backend.positive_score
        response = fixture()
        with patch.object(backend, "positive_score", wraps=real_score) as score:
            result = self.run_probe(response)
            score.assert_called_once()
            self.assertEqual(real_score(score.call_args.args[0]), real_score(diag.object_tree(response)))
        self.assertTrue(result["fixture_score_valid"])
        self.assertEqual(self.events["request"]["arguments_sha256"], diag.digest({
            "model": self.approval["base_deployment"], "messages": self.pair,
            "temperature": 1, "seed": 7, "max_tokens": 1, "logprobs": True, "top_logprobs": 20,
        }))
        self.assertEqual(list(self.events), ["request", "response", "result"])
        self.assertNotIn("PRIVATE", json.dumps(self.events))

    def test_guard_sdk_and_input_failures_never_expose_error_text(self):
        for kwargs, phase in (
            ({"guard_error": ValueError("PRIVATE-GUARD")}, "guard"),
            ({"sdk_error": ValueError("PRIVATE-SDK")}, "sdk"),
        ):
            with self.subTest(phase=phase):
                self.events.clear()
                result = self.run_probe(**kwargs)
                self.assertEqual(result["phase"], phase)
                self.assertNotIn("response", self.events)
                self.assertNotIn("PRIVATE", json.dumps(self.events))
        self.assertEqual(self.run_probe()["reason"], "fake_transport_reached")
        self.pair[0]["content"] = "wrong"
        self.assertEqual(self.run_probe()["phase"], "input")

    def test_response_failures_use_frozen_scoring_and_safe_reason_codes(self):
        mutations = [
            ("choice_count", lambda r: r.update(choices=[])),
            ("refused_or_filtered", lambda r: r["choices"][0]["message"].update(refusal="PRIVATE-REFUSAL")),
            ("binary_output_or_logprobs", lambda r: r["choices"][0]["message"].update(content="PRIVATE-OUTPUT")),
            ("binary_output_or_logprobs", lambda r: r["choices"][0].update(logprobs=None)),
            ("missing_class_logprobs", lambda r: r["choices"][0]["logprobs"]["content"][0].update(top_logprobs=[])),
            ("conflicting_logprobs", lambda r: r["choices"][0]["logprobs"]["content"][0]["top_logprobs"][1].update(logprob=-.5)),
            ("invalid_logprob", lambda r: r["choices"][0]["logprobs"]["content"][0].update(logprob=float("nan"))),
            ("missing_usage", lambda r: r.update(usage=None)),
            ("invalid_usage", lambda r: r["usage"].update(completion_tokens=2)),
            ("model_mismatch", lambda r: r.update(model="PRIVATE-MODEL")),
        ]
        for reason, mutate in mutations:
            with self.subTest(reason=reason):
                response = fixture()
                mutate(response)
                result = self.run_probe(response)
                self.assertEqual(result["reason"], reason)
                self.assertFalse(result["fixture_score_valid"])
                self.assertNotIn("PRIVATE", json.dumps(self.events, allow_nan=False))
        self.assertEqual(self.events["result"]["phase"], "model_check")

    def test_malformed_fixture_and_failed_diagnostic_write_never_score(self):
        import backend
        with patch.object(backend, "positive_score") as score:
            def fail(name, value):
                if name == "response":
                    raise OSError("PRIVATE-PATH")
            with self.assertRaises(diag.DiagnosticWriteError):
                diag.probe(self.config, self.approval, self.examples, self.pair, fail,
                           diag.object_tree(fixture()))
            score.assert_not_called()
        result = self.run_probe({"choices": [{"message": {}}]})
        self.assertFalse(result["fixture_score_valid"])
        self.assertNotIn("PRIVATE", json.dumps(self.events))

    def test_sdk_rejections_do_not_retry_or_export_provider_bodies(self):
        import openai
        for status in (429, 500):
            with self.subTest(status=status):
                error = openai.APIStatusError("PRIVATE-PROVIDER-BODY")
                error.status_code = status
                error.response = NS(headers={"retry-after": "0"})
                records = []
                result = diag.probe(
                    self.config, self.approval, self.examples, self.pair,
                    lambda name, value: records.append((name, value)), sdk_error=error,
                )
                self.assertEqual([name for name, _ in records], ["request", "result"])
                self.assertEqual(result["phase"], "sdk")
                self.assertNotIn("PRIVATE", json.dumps(records))


class AuditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve()
        self.root = self.directory / "run"
        self.config = {"model": "fixture-model", "text_tokens": 2048}
        self.study = {"config": self.config}
        self.pair = [{"role": "system", "content": "PRIVATE"}, {
            "role": "user", "content": json.dumps({
                "project": diag.PILOT_PROJECT, "question": QUESTION,
                "original_text": "Add a settings page.",
            }, ensure_ascii=False, allow_nan=False),
        }]
        write_json(self.root / "study.json", self.study)
        write_json(self.root / "prepared.json", {"private": True})
        self.approval = {"study_sha256": diag.digest(self.study), "resource_id": "PRIVATE",
                         "base_deployment": "PRIVATE"}
        write_json(self.root / "authorization.json", {
            "approval": self.approval, "prepared_sha256": diag.file_hash(self.root / "prepared.json"),
        })
        self.failure = self.root / "failures/smoke.json"
        self.evidence = {
            "schema": "openai-failure-evidence-v1", "study_sha256": diag.digest(self.study),
            "run": diag.study_id(self.root), "stage": "smoke",
            "dispatch": {"run": diag.study_id(self.root), "operation": "smoke-0", "kind": "inference",
                         "attempt": 1, "request_sha256": diag.digest({
                             "resource_id": "PRIVATE", "model": "fixture-model",
                             "messages_sha256": diag.digest(self.pair), "config_sha256": diag.digest(self.config),
                             "deployment": "PRIVATE", "method": diag.BASE_METHOD,
                         })},
        }
        self.save_failure()
        for mock in (
            patch.object(diag, "frozen_study", return_value=self.config),
            patch.object(diag, "system_message", return_value="PRIVATE"),
            patch.object(diag, "demonstrations", return_value={
                diag.cell_key(diag.PILOT_PROJECT, diag.PILOT_LEVEL, "text"): {"examples": []},
            }),
        ):
            mock.start()
            self.addCleanup(mock.stop)

    def save_failure(self):
        write_json(self.failure, self.evidence)
        write_json(self.root / "status/smoke.json", {
            "status": "failed", "failure_evidence": {
                "path": "failures/smoke.json", "sha256": diag.file_hash(self.failure),
            },
        })

    def test_audit_binds_exact_failure_and_request(self):
        context = diag.audit(self.root, self.failure)[-1]
        self.assertEqual(context["attempt"], 1)
        self.assertEqual(context["request_sha256"], self.evidence["dispatch"]["request_sha256"])
        for field, value in (("attempt", 2), ("operation", "smoke-1"), ("request_sha256", "wrong")):
            with self.subTest(field=field):
                original = copy.deepcopy(self.evidence)
                self.evidence["dispatch"][field] = value
                self.save_failure()
                with self.assertRaises(ValueError):
                    diag.audit(self.root, self.failure)
                self.evidence = original
                self.save_failure()
        write_json(self.failure, {**self.evidence, "tampered": True})
        with self.assertRaisesRegex(ValueError, "saved status"):
            diag.audit(self.root, self.failure)

    def test_cli_writes_only_private_new_simulation_output(self):
        output = self.directory / "diagnostics"
        args = ["--root", str(self.root), "--failure", str(self.failure), "--output", str(output)]
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with patch.object(diag, "probe") as probe, redirect_stdout(io.StringIO()):
            def run(config, approval, examples, pair, record, response):
                result = {"phase": "sdk", "reason": "fake_transport_reached"}
                record("result", result)
                return result
            probe.side_effect = run
            diag.main(args)
            with self.assertRaises(FileExistsError):
                diag.main(args)
            probe.assert_called_once()
        report = diag.read_json(output / "result.json")
        self.assertTrue(report["simulation"])
        self.assertEqual(report["historical_outcome"], "UNKNOWN")
        self.assertFalse(report["cloud_access"])
        self.assertFalse(report["authorizes_execution"])
        self.assertEqual((output.stat().st_mode & 0o777), 0o700)
        self.assertEqual(((output / "result.json").stat().st_mode & 0o777), 0o600)
        self.assertNotIn("PRIVATE", json.dumps(report))
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_changed_preparation_and_in_run_output_stop_before_probe(self):
        with patch.object(diag, "probe") as probe, redirect_stdout(io.StringIO()):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                diag.main(["--root", str(self.root), "--failure", str(self.failure),
                           "--output", str(self.root / "diagnostics")])
            write_json(self.root / "prepared.json", {"changed": True})
            with self.assertRaisesRegex(ValueError, "Authorization provenance"):
                diag.main(["--root", str(self.root), "--failure", str(self.failure),
                           "--output", str(self.directory / "diagnostics")])
            probe.assert_not_called()
        self.assertFalse((self.directory / "diagnostics").exists())


if __name__ == "__main__":
    unittest.main()
