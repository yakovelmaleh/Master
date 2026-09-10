import os
import time
from urllib.parse import urljoin

import requests


class JiraClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/") + "/"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "jira-url-to-instability-model/1.0",
            }
        )
        token = os.environ.get("JIRA_TOKEN")
        email = os.environ.get("JIRA_EMAIL")
        if token and email:
            self.session.auth = (email, token)
        elif token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        self.api_version = self._detect_api_version()

    def _url(self, path):
        return urljoin(self.base_url, path.lstrip("/"))

    def request(self, method, path, **kwargs):
        last_error = None
        for attempt in range(5):
            try:
                response = self.session.request(
                    method,
                    self._url(path),
                    timeout=60,
                    allow_redirects=True,
                    **kwargs,
                )
                if response.status_code not in (429, 502, 503, 504):
                    return response
                last_error = f"HTTP {response.status_code}"
            except requests.RequestException as error:
                last_error = f"{type(error).__name__}: {error}"
            time.sleep(min(20, 2**attempt))
        raise RuntimeError(last_error or "Jira request failed.")

    def json_request(self, method, path, **kwargs):
        response = self.request(method, path, **kwargs)
        if response.status_code >= 400:
            snippet = response.text[:500].replace("\n", " ")
            raise RuntimeError(
                f"HTTP {response.status_code} for {response.url}: {snippet}"
            )
        try:
            return response.json()
        except ValueError as error:
            raise RuntimeError(
                f"Expected JSON from {response.url}, received "
                f"{response.headers.get('content-type', 'unknown')}."
            ) from error

    def _detect_api_version(self):
        for version in (3, 2):
            response = self.request(
                "GET",
                f"/rest/api/{version}/field",
            )
            if (
                response.status_code == 200
                and "json" in response.headers.get("content-type", "")
            ):
                try:
                    payload = response.json()
                except ValueError:
                    continue
                if isinstance(payload, list):
                    return version
        raise RuntimeError(
            f"Could not access Jira REST fields at {self.base_url}."
        )

    def fields(self):
        fields = self.json_request(
            "GET", f"/rest/api/{self.api_version}/field"
        )
        return {field["name"]: field["id"] for field in fields}

    def _search_endpoint(self):
        v2 = self.request(
            "GET",
            "/rest/api/2/search",
            params={"jql": "order by created asc", "maxResults": 1},
        )
        if (
            v2.status_code == 200
            and "json" in v2.headers.get("content-type", "")
        ):
            return "v2", "/rest/api/2/search"
        v3 = self.request(
            "GET",
            "/rest/api/3/search/jql",
            params={"jql": "order by created asc", "maxResults": 1},
        )
        if (
            v3.status_code == 200
            and "json" in v3.headers.get("content-type", "")
        ):
            return "v3", "/rest/api/3/search/jql"
        raise RuntimeError(
            "Neither Jira search endpoint is anonymously accessible."
        )

    def search_issue_keys(self, jql, max_issues=None):
        mode, endpoint = self._search_endpoint()
        start_at = 0
        next_token = None
        keys = []
        while True:
            params = {
                "jql": jql,
                "fields": "key",
                "maxResults": 100,
            }
            if mode == "v2":
                params["startAt"] = start_at
            elif next_token:
                params["nextPageToken"] = next_token
            payload = self.json_request("GET", endpoint, params=params)
            page = payload.get("issues", [])
            keys.extend(issue["key"] for issue in page)
            if max_issues and len(keys) >= max_issues:
                return keys[:max_issues]
            if mode == "v2":
                start_at += len(page)
                if not page or start_at >= payload.get("total", 0):
                    break
            else:
                next_token = payload.get("nextPageToken")
                if not next_token:
                    break
        return keys

    def issue(self, key, field_ids):
        return self.json_request(
            "GET",
            f"/rest/api/{self.api_version}/issue/{key}",
            params={"fields": ",".join(field_ids)},
        )

    def comments(self, key):
        comments = []
        start_at = 0
        while True:
            payload = self.json_request(
                "GET",
                f"/rest/api/{self.api_version}/issue/{key}/comment",
                params={"startAt": start_at, "maxResults": 100},
            )
            page = payload.get("comments", [])
            comments.extend(page)
            start_at += len(page)
            if not page or start_at >= payload.get("total", len(comments)):
                break
        return comments

    def changelog(self, key):
        changes = []
        start_at = 0
        while True:
            response = self.request(
                "GET",
                f"/rest/api/{self.api_version}/issue/{key}/changelog",
                params={"startAt": start_at, "maxResults": 100},
            )
            if response.status_code in (404, 405):
                issue = self.json_request(
                    "GET",
                    f"/rest/api/{self.api_version}/issue/{key}",
                    params={"expand": "changelog", "fields": "key"},
                )
                return (issue.get("changelog") or {}).get("histories", [])
            if response.status_code >= 400:
                raise RuntimeError(
                    f"HTTP {response.status_code} loading changelog for {key}."
                )
            payload = response.json()
            page = payload.get("values", payload.get("histories", []))
            changes.extend(page)
            start_at += len(page)
            if payload.get("isLast") is True:
                break
            if not page or start_at >= payload.get("total", len(changes)):
                break
        return changes
