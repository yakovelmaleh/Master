"""Azure-only network boundary. No SDK retries on non-idempotent training calls."""

import math
import time
from urllib.parse import quote

from protocol import PROMPT, prompt_only, require_sft


class ProviderError(RuntimeError):
    """A sanitized provider failure safe to display in cluster logs."""


def positive_score(response):
    if len(response.choices) != 1:
        raise ValueError("Expected one classification choice.")
    choice = response.choices[0]
    if choice.finish_reason not in ("stop", "length") or choice.message.refusal:
        raise ValueError("Classification was refused or filtered.")
    if choice.message.content not in ("0", "1") or not choice.logprobs or not choice.logprobs.content:
        raise ValueError("Expected an exact binary token and its log probabilities.")
    if len(choice.logprobs.content) != 1:
        raise ValueError("Classification must contain exactly one scored token.")
    token = choice.logprobs.content[0]
    if token.token != choice.message.content:
        raise ValueError("Output and scored token disagree.")
    values = {}
    for item in [token, *token.top_logprobs]:
        if item.token in ("0", "1"):
            if not math.isfinite(item.logprob) or item.logprob > 0:
                raise ValueError("Invalid class log probability.")
            if item.token in values and values[item.token] != item.logprob:
                raise ValueError("Conflicting class log probabilities.")
            values[item.token] = item.logprob
    if set(values) != {"0", "1"}:
        raise ValueError("Both class log probabilities are required; no probability fallback.")
    maximum = max(values.values())
    zero, one = math.exp(values["0"] - maximum), math.exp(values["1"] - maximum)
    if response.usage is None:
        raise ValueError("Provider did not return token usage.")
    usage = {"input_tokens": response.usage.prompt_tokens, "output_tokens": response.usage.completion_tokens}
    if any(type(value) is not int or value < 0 for value in usage.values()) or usage["output_tokens"] != 1:
        raise ValueError("Unexpected provider token accounting.")
    # With max_tokens=1, length is normal if the single class token is complete.
    return {"score": one / (zero + one), "usage": usage,
            "response_model": response.model, "request_id": response.id}


class AzureBackend:
    def __init__(self, approval, config):
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        from openai import OpenAI
        import httpx

        self.approval, self.config = approval, config
        self.credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        self.client = OpenAI(
            base_url=approval["endpoint"].rstrip("/") + "/openai/v1/",
            api_key=get_bearer_token_provider(self.credential, "https://cognitiveservices.azure.com/.default"),
            max_retries=0, timeout=60,
        )
        self.http = httpx.Client(timeout=60, follow_redirects=False)
        self.guard = None

    def before_mutation(self):
        if self.guard is None:
            raise ValueError("A durable cloud dispatch guard is required.")
        self.guard()

    def arm(self, method, suffix="", body=None, missing_ok=False):
        if method != "GET":
            require_sft(self.config)
        url = "https://management.azure.com" + self.approval["resource_id"] + suffix
        token = self.credential.get_token("https://management.azure.com/.default").token
        if method != "GET":
            self.before_mutation()
        response = self.http.request(method, url, params={"api-version": "2024-10-01"},
                                     headers={"Authorization": "Bearer " + token}, json=body)
        if missing_ok and response.status_code == 404:
            return None
        if not response.is_success:
            raise ProviderError(f"Azure management request failed (HTTP {response.status_code}).")
        return response.json() if response.content else {}

    def preflight(self):
        account = self.arm("GET")
        endpoint = account["properties"]["endpoint"].rstrip("/").casefold()
        if endpoint != self.approval["endpoint"].rstrip("/").casefold():
            raise ValueError("Azure management account and inference endpoint differ.")
        base = self.get_deployment(self.approval["base_deployment"])
        model = base["properties"]["model"]
        expected = self.config["model"]
        if model["name"] + "-" + model["version"] != expected:
            raise ValueError("Existing base deployment must match the exact model snapshot.")
        if base["properties"]["provisioningState"] != "Succeeded":
            raise ValueError("Base deployment is not ready.")
        if prompt_only(self.config) and base["sku"]["name"] != self.config["deployment_sku"]:
            raise ValueError("Base deployment billing SKU differs from the prompt-only approval.")
        # Also exercise data-plane authorization without inference charges.
        self.client.models.list()
        return {"account_verified": True, "base_model_verified": expected,
                "data_plane_access": True, "location": account["location"]}

    def upload(self, path, filename):
        require_sft(self.config)
        with path.open("rb") as stream:
            self.before_mutation()
            item = self.client.files.create(file=(filename, stream), purpose="fine-tune")
        return item.id

    def find_upload(self, filename):
        found = [item.id for item in self.client.files.list(purpose="fine-tune") if item.filename == filename]
        if len(found) != 1:
            raise ValueError("Upload outcome ambiguous; reconcile files in the approved Azure account.")
        return found[0]

    def wait_file(self, training_file):
        self.client.files.wait_for_processing(training_file)

    def train(self, training_file, suffix):
        require_sft(self.config)
        self.before_mutation()
        result = self.client.fine_tuning.jobs.create(
            model=self.config["model"], training_file=training_file, suffix=suffix,
            seed=self.config["seed"],
            method={"type": "supervised", "supervised": {"hyperparameters": {
                "n_epochs": self.config["epochs"], "batch_size": "auto", "learning_rate_multiplier": "auto",
            }}},
            extra_body={"trainingType": self.config["training_type"]},
        )
        return self.job_value(result)

    @staticmethod
    def job_value(job):
        return {"id": job.id, "status": job.status, "model": job.model,
                "training_file": job.training_file, "fine_tuned_model": job.fine_tuned_model,
                "trained_tokens": job.trained_tokens}

    def find_job(self, file_id):
        jobs = [job for job in self.client.fine_tuning.jobs.list(limit=100)
                if job.training_file == file_id and job.model == self.config["model"]]
        if len(jobs) != 1:
            raise ValueError("Training submission unconfirmed; do not resubmit or release its reservation.")
        return self.job_value(jobs[0])

    def job(self, job_id):
        return self.job_value(self.client.fine_tuning.jobs.retrieve(job_id))

    def cancel(self, job_id):
        require_sft(self.config)
        self.before_mutation()
        return self.job_value(self.client.fine_tuning.jobs.cancel(job_id))

    def get_deployment(self, name):
        return self.arm("GET", "/deployments/" + quote(name, safe=""), missing_ok=True)

    def deploy(self, name, model, owner):
        require_sft(self.config)
        self.arm("PUT", "/deployments/" + quote(name, safe=""), {
            "sku": {"name": self.config["deployment_sku"], "capacity": self.config["deployment_capacity"]},
            "tags": {"master-study": owner},
            "properties": {"model": {"format": "OpenAI", "name": model, "version": "1"},
                           "versionUpgradeOption": "NoAutoUpgrade"},
        })

    def ready(self, name, model, owner):
        for _ in range(40):
            value = self.get_deployment(name)
            if value is not None:
                if (value["properties"]["model"]["name"] != model or
                        value.get("tags", {}).get("master-study") != owner or
                        value["sku"]["name"] != self.config["deployment_sku"]):
                    raise ValueError("Deployment ownership, model, or billing SKU differs.")
                state = value["properties"]["provisioningState"]
                if state == "Succeeded":
                    if value["sku"].get("capacity") != self.config["deployment_capacity"]:
                        raise ValueError("Deployment capacity differs from the approved configuration.")
                    return
                if state in ("Failed", "Canceled"):
                    raise ValueError("Azure deployment failed.")
            time.sleep(15)
        raise TimeoutError("Deployment not ready; resume rather than creating a different model.")

    def remove_deployment(self, name):
        require_sft(self.config)
        self.arm("DELETE", "/deployments/" + quote(name, safe=""), missing_ok=True)
        for _ in range(40):
            if self.get_deployment(name) is None:
                return
            time.sleep(15)
        raise TimeoutError("Deployment deletion is unconfirmed.")

    def predict(self, deployment, messages):
        from openai import APIConnectionError, APIStatusError
        from cloud_control import RetryableRejection

        if prompt_only(self.config) and (
            deployment != self.approval["base_deployment"]
            or [item.get("role") for item in messages] != ["system", "user"]
            or messages[0].get("content") != PROMPT
        ):
            raise ValueError("Prompt-only inference requires the approved base and exact system/user prompt.")
        self.before_mutation()
        try:
            response = self.client.chat.completions.create(
                model=deployment, messages=messages, temperature=1, seed=self.config["seed"],
                max_tokens=1, logprobs=True, top_logprobs=self.config["top_logprobs"],
            )
            result = positive_score(response)
            if prompt_only(self.config) and result["response_model"] != self.config["model"]:
                raise ValueError("Inference returned a different base model snapshot; retain the dispatch.")
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

    def delete_file(self, file_id):
        require_sft(self.config)
        from openai import NotFoundError

        try:
            self.before_mutation()
            self.client.files.delete(file_id)
        except NotFoundError:
            pass  # An already absent, manifest-owned file is cleaned up.

    def delete_model(self, model):
        require_sft(self.config)
        from openai import NotFoundError

        try:
            self.before_mutation()
            self.client.models.delete(model)
        except NotFoundError:
            pass  # An already absent, manifest-owned model is cleaned up.

    def file_exists(self, file_id):
        from openai import NotFoundError
        try:
            self.client.files.retrieve(file_id)
        except NotFoundError:
            return False
        return True

    def model_exists(self, model):
        from openai import NotFoundError
        try:
            self.client.models.retrieve(model)
        except NotFoundError:
            return False
        return True

    def close(self):
        self.client.close()
        self.http.close()
        self.credential.close()
