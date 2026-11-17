"""Reuse the frozen Azure transport, replacing only the exact prompt contract."""

import json
import math

from sufficiency import QUESTION
from azure_backend import AzureBackend, ProviderError, positive_score
from cloud_control import RetryableRejection
from protocol import PROJECTS


class SufficiencyBackend(AzureBackend):
    def __init__(self, approval, config, examples):
        self.systems = {
            entry["system"]: (entry["project"], entry["variant"]) for entry in examples.values()
        }
        super().__init__(approval, config)

    def predict(self, deployment, messages):
        from openai import APIConnectionError, APIStatusError

        if (deployment != self.approval["base_deployment"]
                or [item.get("role") for item in messages] != ["system", "user"]
                or messages[0].get("content") not in self.systems):
            raise ValueError("Exact sufficiency system/user messages and approved deployment required.")
        payload = json.loads(messages[1]["content"])
        fields = {"project", "question", "original_text"}
        if (set(payload) not in (fields, fields | {"train_fitted_structured_features"})
                or payload["project"] not in PROJECTS or payload["question"] != QUESTION
                or not isinstance(payload["original_text"], str)):
            raise ValueError("Unexpected sufficiency input; labels and K cannot be prompt metadata.")
        project, variant = self.systems[messages[0]["content"]]
        if (payload["project"] != project
                or ("train_fitted_structured_features" in payload) != (variant == "structured")):
            raise ValueError("Training examples differ from the target project or input variant.")
        self.before_mutation()
        try:
            response = self.client.chat.completions.create(
                model=deployment, messages=messages, temperature=1, seed=self.config["seed"],
                max_tokens=1, logprobs=True, top_logprobs=self.config["top_logprobs"],
            )
            result = positive_score(response)
            if result["response_model"] != self.config["model"]:
                raise ValueError("Inference returned a different model snapshot; retain the dispatch.")
            return result
        except (APIConnectionError, APIStatusError) as error:
            status = getattr(error, "status_code", None)
            if status == 429:
                response = getattr(error, "response", None)
                header = response.headers.get("retry-after") if response is not None else None
                delay = float(header) if header and header.replace(".", "", 1).isdigit() else 1
                if math.isfinite(delay) and 0 <= delay <= 120:
                    raise RetryableRejection(delay) from None
            raise ProviderError(
                f"Inference failed (HTTP {status}); outcome retained, no automatic replay."
            ) from None
