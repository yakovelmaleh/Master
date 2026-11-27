import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK))
import numeric_diagnostics as diag
from backend import SufficiencyBackend
from sufficiency import QUESTION


class NumericTests(unittest.TestCase):
    def test_exact_floats_signed_zero_and_strict_json_nonfinite_categories(self):
        cases = [
            (-.2, "negative"), (1e-12, "positive"), (5e-324, "positive"),
            (0., "zero"), (-0., "zero"), (-9999., "negative"),
            (float("nan"), "nan"), (float("inf"), "positive_infinity"),
            (float("-inf"), "negative_infinity"),
        ]
        for value, category in cases:
            with self.subTest(category=category, value=value):
                result = json.loads(json.dumps(diag.numeric_value(value), allow_nan=False))
                self.assertEqual(result["category"], category)
                self.assertEqual(result["hex"], value.hex())
                if category in ("positive", "negative", "zero"):
                    self.assertEqual(float.fromhex(result["hex"]).hex(), value.hex())
        self.assertNotEqual(diag.numeric_value(-0.)["hex"], diag.numeric_value(0.)["hex"])

    def test_generated_and_top_values_preserve_duplicates_and_conflicts(self):
        response = diag.synthetic_response("conflicting")
        evidence = diag.response_evidence(response, "synthetic-model")
        self.assertEqual([(entry["source"], entry["index"], entry["label"]) for entry in evidence["class_logprobs"]],
                         [("generated", None, "1"), ("top_logprobs", 0, "0"),
                          ("top_logprobs", 1, "1"), ("top_logprobs", 2, "0")])
        self.assertEqual([entry["logprob"]["value"] for entry in evidence["class_logprobs"]],
                         ["-0.2", "-1.7", "-0.2", "-2.0"])
        self.assertEqual(evidence["usage"], {"input_tokens": 30, "output_tokens": 1})

    def test_non_numeric_values_and_unrelated_tokens_never_leak_raw_fields(self):
        class Private:
            def __repr__(self):
                raise AssertionError("Never stringify unexpected provider objects")
        for value, kind in ((None, "null"), (True, "bool"), ("PRIVATE", "str"), (Private(), "other")):
            with self.subTest(kind=kind):
                self.assertEqual(diag.numeric_value(value), {"type": kind, "category": "non_numeric"})
        response = diag.synthetic_response("valid")
        response.id = response.model = "PRIVATE"
        response.choices[0].message.content = response.choices[0].message.refusal = "PRIVATE"
        response.choices[0].finish_reason = "PRIVATE"
        top = response.choices[0].logprobs.content[0].top_logprobs
        top[0].logprob = "PRIVATE"
        top.append(NS(token="PRIVATE", logprob=Private(), bytes="PRIVATE"))
        evidence = diag.response_evidence(response, "synthetic-model")
        self.assertNotIn("PRIVATE", json.dumps(evidence, allow_nan=False))
        self.assertIsNone(evidence["output_label"])
        self.assertFalse(evidence["expected_model_match"])
        self.assertEqual(len(evidence["class_logprobs"]), 3)

    def test_malformed_shape_is_bounded_and_capture_does_not_invent_values(self):
        for response in (NS(), NS(choices=[]), NS(choices=[NS(message=NS())]),
                         NS(choices=[NS(logprobs=NS(content=[]))])):
            with self.subTest(response=response):
                evidence = diag.response_evidence(response, "synthetic-model")
                self.assertEqual(evidence["class_logprobs"], [])
                json.dumps(evidence, allow_nan=False)
        response = diag.synthetic_response("missing-class")
        evidence = diag.response_evidence(response, "synthetic-model")
        self.assertEqual({entry["label"] for entry in evidence["class_logprobs"]}, {"1"})

    def test_oversized_capture_or_failed_write_stops_before_scoring(self):
        for oversized in ("alternatives", "integer"):
            with self.subTest(oversized=oversized):
                response = diag.synthetic_response("valid")
                token = response.choices[0].logprobs.content[0]
                if oversized == "alternatives":
                    token.top_logprobs *= 11
                else:
                    token.logprob = 2 ** 2048
                record, score = Mock(), Mock()
                with self.assertRaises(diag.CaptureError):
                    score(diag.capture_response(response, "synthetic-model", record))
                score.assert_not_called()
                record.assert_called_once()
                evidence = record.call_args.args[0]
                self.assertFalse(evidence["capture_complete"])
                self.assertLessEqual(len(evidence["class_logprobs"]), 21)
                json.dumps(evidence, allow_nan=False)
        with patch.object(diag.os, "fsync", side_effect=OSError("PRIVATE")):
            with tempfile.TemporaryDirectory() as temporary, self.assertRaises(diag.CaptureError):
                diag.capture_response(diag.synthetic_response("valid"), "synthetic-model",
                                      lambda value: diag.exclusive_json(Path(temporary) / "response.json", value))

    def test_capture_is_before_frozen_backend_scoring_without_mutation_or_retry(self):
        config = {"model": "synthetic-model", "seed": 7, "top_logprobs": 20}
        messages = [{"role": "system", "content": "PRIVATE-SYSTEM"}, {"role": "user", "content": json.dumps({
            "project": "Jira", "question": QUESTION, "original_text": "PRIVATE-STORY",
        })}]
        sdk = NS(APIConnectionError=type("APIConnectionError", (Exception,), {}),
                 APIStatusError=type("APIStatusError", (Exception,), {}))
        for case in diag.CASES:
            with self.subTest(case=case), patch.dict(sys.modules, {"openai": sdk}):
                response = diag.synthetic_response(case)
                original = copy.deepcopy(response)
                events = []
                backend = SufficiencyBackend.__new__(SufficiencyBackend)
                backend.config, backend.approval = config, {"base_deployment": "PRIVATE-DEPLOYMENT"}
                backend.systems = {"PRIVATE-SYSTEM": ("Jira", "text")}
                backend.guard = lambda: None
                def create(**kwargs):
                    events.append("create")
                    return diag.capture_response(response, config["model"],
                                                 lambda value: events.append(value))
                create_mock = Mock(side_effect=create)
                backend.client = NS(chat=NS(completions=NS(create=create_mock)))
                def score(value):
                    self.assertIs(value, response)
                    self.assertEqual(len(events), 2)
                    events.append("score")
                    return diag.positive_score(value)
                with patch("backend.positive_score", side_effect=score) as scorer:
                    try:
                        expected = diag.positive_score(original)
                    except Exception as error:
                        with self.assertRaises(type(error)) as actual:
                            backend.predict("PRIVATE-DEPLOYMENT", messages)
                        self.assertEqual(str(actual.exception), str(error))
                    else:
                        self.assertEqual(backend.predict("PRIVATE-DEPLOYMENT", messages), expected)
                    scorer.assert_called_once()
                create_mock.assert_called_once_with(
                    model="PRIVATE-DEPLOYMENT", messages=messages, temperature=1, seed=7,
                    max_tokens=1, logprobs=True, top_logprobs=20,
                )
                self.assertEqual(diag.response_evidence(response, config["model"]),
                                 diag.response_evidence(original, config["model"]))
                self.assertNotIn("PRIVATE", json.dumps(events[1], allow_nan=False))

    def test_frozen_backend_never_scores_when_numeric_persistence_fails(self):
        backend = SufficiencyBackend.__new__(SufficiencyBackend)
        backend.config = {"model": "synthetic-model", "seed": 7, "top_logprobs": 20}
        backend.approval = {"base_deployment": "fixture"}
        backend.systems, backend.guard = {"system": ("Jira", "text")}, lambda: None
        record = Mock(side_effect=OSError("PRIVATE"))
        backend.client = NS(chat=NS(completions=NS(create=Mock(side_effect=lambda **kwargs: diag.capture_response(
            diag.synthetic_response("valid"), "synthetic-model", record,
        )))))
        sdk = NS(APIConnectionError=type("APIConnectionError", (Exception,), {}),
                 APIStatusError=type("APIStatusError", (Exception,), {}))
        with patch.dict(sys.modules, {"openai": sdk}), patch("backend.positive_score") as score:
            with self.assertRaises(diag.CaptureError):
                backend.predict("fixture", [{"role": "system", "content": "system"}, {
                    "role": "user", "content": json.dumps({
                        "project": "Jira", "question": QUESTION, "original_text": "story",
                    }),
                }])
            score.assert_not_called()
            backend.client.chat.completions.create.assert_called_once()


class CliTests(unittest.TestCase):
    def test_synthetic_cli_is_offline_private_and_exclusive_for_every_case(self):
        with tempfile.TemporaryDirectory() as temporary:
            for case in diag.CASES:
                output = Path(temporary).resolve() / case
                args = ["--case", case, "--output", str(output)]
                with self.subTest(case=case), patch.dict(
                    sys.modules, {"openai": None, "azure.identity": None}
                ), patch("socket.create_connection", side_effect=AssertionError("No network")), redirect_stdout(
                    io.StringIO()
                ):
                    diag.main(args)
                    with self.assertRaises(FileExistsError):
                        diag.main(args)
                response = json.loads((output / "response.json").read_text())
                result = json.loads((output / "result.json").read_text())
                self.assertEqual(result["scorer_accepted"], case == "valid")
                self.assertTrue(response["simulation"])
                self.assertFalse(response["cloud_access"])
                self.assertFalse(response["historical_response_recovered"])
                self.assertFalse(response["authorizes_execution"])
                self.assertEqual(output.stat().st_mode & 0o777, 0o700)
                for path in output.iterdir():
                    self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                    json.dumps(json.loads(path.read_text()), allow_nan=False)


if __name__ == "__main__":
    unittest.main()
