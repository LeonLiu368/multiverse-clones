from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_URL = "http://gauge"
DEFAULT_TOKEN = "test-token-acme-eval"


class GaugeClientError(RuntimeError):
    exit_code = 1


class NotFoundError(GaugeClientError):
    exit_code = 2


class AuthConfigError(GaugeClientError):
    exit_code = 3


class BackendUnavailableError(GaugeClientError):
    exit_code = 5


class UnsupportedCommandError(GaugeClientError):
    exit_code = 6


def _token() -> str:
    return os.environ.get("GRAFANA_SERVICE_ACCOUNT_TOKEN") or os.environ.get("GRAFANA_TOKEN") or DEFAULT_TOKEN


def _admin_token() -> str:
    token = os.environ.get("GAUGE_ADMIN_TOKEN")
    if not token:
        raise AuthConfigError("GAUGE_ADMIN_TOKEN is required for Gauge admin API access")
    return token


def _base_url() -> str:
    return (os.environ.get("GRAFANA_URL") or os.environ.get("GRAFANA_SERVER") or DEFAULT_URL).rstrip("/")


class GaugeClient:
    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or _base_url()).rstrip("/")
        self.token = token or _token()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        url = self.base_url + path
        if params:
            query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})
            if query:
                url += "?" + query
        data = None
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self.token}"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            message = _error_message(body) or exc.reason
            if exc.code in (401, 403):
                raise AuthConfigError(message)
            if exc.code == 404:
                raise NotFoundError(message)
            if exc.code >= 500:
                raise BackendUnavailableError(message)
            raise GaugeClientError(message)
        except urllib.error.URLError as exc:
            raise BackendUnavailableError(str(exc.reason)) from exc

    def health(self) -> dict[str, Any]:
        url = self.base_url + "/api/healthz"
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise BackendUnavailableError(str(exc.reason)) from exc

    def config_check(self) -> dict[str, Any]:
        health = self.health()
        user = self.user()
        return {
            "ok": True,
            "url": self.base_url,
            "token_configured": bool(self.token),
            "health": health,
            "user": user,
        }

    def user(self) -> dict[str, Any]:
        return self.request("GET", "/api/user")

    def org(self) -> dict[str, Any]:
        return self.request("GET", "/api/org")

    def search_dashboards(self, query: str | None = None) -> list[dict[str, Any]]:
        return self.request("GET", "/api/search", params={"query": query, "type": "dash-db"})

    def dashboard(self, uid: str) -> dict[str, Any]:
        return self.request("GET", f"/api/dashboards/uid/{urllib.parse.quote(uid)}")

    def dashboard_summary(self, uid: str) -> dict[str, Any]:
        data = self.dashboard(uid)
        dashboard = data.get("dashboard", {})
        meta = data.get("meta", {})
        panels = dashboard.get("panels") or []
        return {
            "uid": dashboard.get("uid"),
            "title": dashboard.get("title"),
            "folder": meta.get("folderTitle"),
            "tags": dashboard.get("tags", []),
            "panel_count": len(panels),
            "panels": [
                {
                    "id": panel.get("id"),
                    "title": panel.get("title"),
                    "type": panel.get("type"),
                    "datasource_uid": panel.get("datasource_uid"),
                    "query": panel.get("query"),
                }
                for panel in panels
            ],
        }

    def dashboard_panels(self, uid: str) -> list[dict[str, Any]]:
        data = self.dashboard(uid)
        return data.get("dashboard", {}).get("panels", [])

    def datasources(self) -> list[dict[str, Any]]:
        return self.request("GET", "/api/datasources")

    def datasource(self, uid: str) -> dict[str, Any]:
        return self.request("GET", f"/api/datasources/uid/{urllib.parse.quote(uid)}")

    def datasource_health(self, uid: str) -> dict[str, Any]:
        datasource = self.datasource(uid)
        return {
            "uid": datasource.get("uid"),
            "status": datasource.get("health", "ok"),
            "message": f"{datasource.get('type', 'datasource')} datasource is {datasource.get('health', 'ok')}",
        }

    def ds_query(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/api/ds/query", payload=payload)

    def query_metrics(
        self,
        expr: str,
        datasource_uid: str | None = None,
        since: str | None = None,
        step: str | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
    ) -> dict[str, Any]:
        return self._first_query_result(
            {
                "queries": [
                    {
                        "refId": "A",
                        "queryType": "metrics",
                        "datasource": {"uid": datasource_uid} if datasource_uid else {},
                        "expr": expr,
                        "since": since,
                        "step": step,
                        "from": from_time,
                        "to": to_time,
                    }
                ]
            }
        )

    def metric_names(self, datasource_uid: str | None = None) -> dict[str, Any]:
        return self._first_query_result({"queries": [{"refId": "A", "queryType": "metric_names", "datasource": {"uid": datasource_uid} if datasource_uid else {}}]})

    def metric_labels(self, datasource_uid: str | None = None) -> dict[str, Any]:
        return self._first_query_result({"queries": [{"refId": "A", "queryType": "metric_labels", "datasource": {"uid": datasource_uid} if datasource_uid else {}}]})

    def metric_label_values(self, label: str, datasource_uid: str | None = None) -> dict[str, Any]:
        return self._first_query_result({"queries": [{"refId": "A", "queryType": "metric_label_values", "label": label, "datasource": {"uid": datasource_uid} if datasource_uid else {}}]})

    def query_logs(
        self,
        expr: str,
        datasource_uid: str | None = None,
        since: str | None = None,
        limit: int | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
    ) -> dict[str, Any]:
        return self._first_query_result(
            {
                "queries": [
                    {
                        "refId": "A",
                        "queryType": "logs",
                        "datasource": {"uid": datasource_uid} if datasource_uid else {},
                        "expr": expr,
                        "since": since,
                        "limit": limit,
                        "from": from_time,
                        "to": to_time,
                    }
                ]
            }
        )

    def log_labels(self, datasource_uid: str | None = None) -> dict[str, Any]:
        return self._first_query_result({"queries": [{"refId": "A", "queryType": "log_labels", "datasource": {"uid": datasource_uid} if datasource_uid else {}}]})

    def log_label_values(self, label: str, datasource_uid: str | None = None) -> dict[str, Any]:
        return self._first_query_result({"queries": [{"refId": "A", "queryType": "log_label_values", "label": label, "datasource": {"uid": datasource_uid} if datasource_uid else {}}]})

    def alert_rules(self, state: str | None = None) -> list[dict[str, Any]]:
        return self.request("GET", "/api/alert-rules", params={"state": state})

    def alert_rule(self, uid: str) -> dict[str, Any]:
        return self.request("GET", f"/api/alert-rules/{urllib.parse.quote(uid)}")

    def alert_instances(self, state: str | None = None) -> list[dict[str, Any]]:
        return self.request("GET", "/api/alert-instances", params={"state": state})

    def alert_history(self, uid: str) -> list[dict[str, Any]]:
        return self.request("GET", f"/api/alert-rules/{urllib.parse.quote(uid)}/history")

    def annotations(self, dashboard_uid: str | None = None, tags: str | None = None) -> list[dict[str, Any]]:
        return self.request("GET", "/api/annotations", params={"dashboardUID": dashboard_uid, "tags": tags})

    def create_annotation(self, dashboard_uid: str, text: str, panel_id: int | None = None, tags: list[str] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"dashboardUID": dashboard_uid, "text": text, "tags": tags or []}
        if panel_id is not None:
            payload["panelId"] = panel_id
        return self.request("POST", "/api/annotations", payload=payload)

    def clone_state(self) -> dict[str, Any]:
        return self.request("GET", "/api/_clone/state")

    def clone_mutations(self) -> list[dict[str, Any]]:
        return self.request("GET", "/api/_clone/mutations")

    def dashboard_variables(self, uid: str) -> list[dict[str, Any]]:
        data = self.dashboard(uid).get("dashboard", {})
        templating = data.get("templating") or {}
        if isinstance(templating, dict) and isinstance(templating.get("list"), list):
            return templating["list"]
        return data.get("variables") or []

    def query_dashboard_panel(
        self,
        uid: str,
        panel_id: int,
        since: str | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
    ) -> dict[str, Any]:
        panels = self.dashboard_panels(uid)
        panel = next((item for item in panels if int(item.get("id", -1)) == int(panel_id)), None)
        if panel is None:
            raise NotFoundError(f"panel not found: {uid}/{panel_id}")
        datasource_uid = panel.get("datasource_uid")
        datasource = self.datasource(str(datasource_uid)) if datasource_uid else {}
        expr = str(panel.get("query") or "")
        if datasource.get("type") == "loki":
            result = self.query_logs(expr, str(datasource_uid) if datasource_uid else None, since, from_time=from_time, to_time=to_time)
        else:
            result = self.query_metrics(expr, str(datasource_uid) if datasource_uid else None, since, from_time=from_time, to_time=to_time)
        return {"dashboard_uid": uid, "panel_id": panel_id, "panel": panel, "result": result}

    def _first_query_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.ds_query(payload)
        result = response.get("results", {}).get("A", {})
        if result.get("status", 200) >= 400:
            raise GaugeClientError(result.get("error", "query failed"))
        return result.get("data", {})


def _error_message(body: str) -> str | None:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return body or None
    for key in ("message", "error"):
        if data.get(key):
            return str(data[key])
    return None


class GaugeAdminClient(GaugeClient):
    def __init__(self, base_url: str | None = None, token: str | None = None):
        super().__init__(base_url=base_url, token=token or _admin_token())
