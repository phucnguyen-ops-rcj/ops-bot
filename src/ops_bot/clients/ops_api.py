from __future__ import annotations

import json
import shlex
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from ops_bot.settings import get_settings

_settings = get_settings()
DEFAULT_OPS_BASE_ENDPOINT = _settings.rcj_ops_base_endpoint
DEFAULT_OPS_TIMEOUT_SECONDS = _settings.rcj_ops_timeout_seconds
DEFAULT_OPS_EXECUTION_MODE: Literal["ssh", "local"] = _settings.rcj_ops_execution_mode
DEFAULT_OPS_SSH_HOST = _settings.rcj_ops_ssh_host


@dataclass(frozen=True)
class OpsApiResponse:
    endpoint: str
    status: int
    body: str
    payload: dict[str, Any]

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def as_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "status": self.status,
            "ok": self.ok,
            "payload": self.payload,
            "body": self.body,
        }


class OpsApiClient:
    def __init__(
        self,
        base_endpoint: str = DEFAULT_OPS_BASE_ENDPOINT,
        timeout_seconds: int = DEFAULT_OPS_TIMEOUT_SECONDS,
        execution_mode: Literal["ssh", "local"] = DEFAULT_OPS_EXECUTION_MODE,
        ssh_host: str = DEFAULT_OPS_SSH_HOST,
    ) -> None:
        self.base_endpoint = base_endpoint
        self.timeout_seconds = timeout_seconds
        self.execution_mode = execution_mode
        self.ssh_host = ssh_host

    def require_token(self) -> str:
        token = get_settings().rcj_ops_bearer_token.strip()
        if not token:
            raise RuntimeError("RCJ_OPS_BEARER_TOKEN is not set.")
        return token

    def post(self, endpoint: str, payload: dict[str, Any]) -> OpsApiResponse:
        return self.request("POST", endpoint, payload, authenticated=True)

    def get(self, endpoint: str) -> OpsApiResponse:
        return self.request("GET", endpoint, {}, authenticated=False)

    def request(
        self,
        method: Literal["GET", "POST"],
        endpoint: str,
        payload: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> OpsApiResponse:
        request_payload = payload or {}
        try:
            if self.execution_mode == "ssh":
                response = self._request_via_ssh(
                    method, endpoint, request_payload, authenticated
                )
            else:
                response = self._request_local(
                    method, endpoint, request_payload, authenticated
                )
        except Exception as exc:
            self._append_ops_log(
                method=method,
                endpoint=endpoint,
                payload=request_payload,
                authenticated=authenticated,
                status=0,
                body=f"request failed: {exc}",
            )
            raise

        self._append_ops_log(
            method=method,
            endpoint=response.endpoint,
            payload=request_payload,
            authenticated=authenticated,
            status=response.status,
            body=response.body,
        )
        return response

    def _request_local(
        self,
        method: Literal["GET", "POST"],
        endpoint: str,
        payload: dict[str, Any],
        authenticated: bool,
    ) -> OpsApiResponse:
        normalized_endpoint = f"/{endpoint.lstrip('/')}"
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self.require_token()}"
        request = urllib.request.Request(
            f"{self.base_endpoint.rstrip('/')}{normalized_endpoint}",
            data=json.dumps(payload).encode("utf-8") if method == "POST" else None,
            method=method,
            headers=headers,
        )

        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds
            ) as response:
                body = response.read().decode("utf-8", errors="replace")
                return OpsApiResponse(
                    endpoint=normalized_endpoint,
                    status=response.status,
                    body=body,
                    payload=payload,
                )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return OpsApiResponse(
                endpoint=normalized_endpoint,
                status=exc.code,
                body=body,
                payload=payload,
            )

    def _request_via_ssh(
        self,
        method: Literal["GET", "POST"],
        endpoint: str,
        payload: dict[str, Any],
        authenticated: bool,
    ) -> OpsApiResponse:
        normalized_endpoint = f"/{endpoint.lstrip('/')}"
        url = f"{self.base_endpoint.rstrip()}{normalized_endpoint}"
        payload_json = json.dumps(payload)
        headers = ""
        if authenticated:
            headers += f" -H {shlex.quote(f'Authorization: Bearer {self.require_token()}')} \\\n"
        if method == "POST":
            headers += " -H 'Content-Type: application/json' \\\n"
        data_arg = f" -d {shlex.quote(payload_json)}" if method == "POST" else ""
        curl_script = f"""curl -sS -w '\\n__RCJ_HTTP_STATUS__:%{{http_code}}\\n' \\
        -X {method} {shlex.quote(url)} \\
        {headers} --max-time {int(self.timeout_seconds)}{data_arg}
        curl_exit=$?
        printf '\\n__RCJ_CURL_EXIT__:%s\\n' "$curl_exit"
        """
        completed = subprocess.run(
            ["ssh", "-q", "-T", self.ssh_host],
            input=curl_script,
            capture_output=True,
            check=False,
            encoding="utf-8",
            timeout=self.timeout_seconds + 15,
        )
        if completed.returncode != 0:
            body = completed.stderr.strip() or completed.stdout.strip()
            return OpsApiResponse(
                endpoint=normalized_endpoint,
                status=0,
                body=f"ssh command failed with exit {completed.returncode}: {body}",
                payload=payload,
            )

        exit_marker = "\n__RCJ_CURL_EXIT__:"
        status_marker = "\n__RCJ_HTTP_STATUS__:"
        if exit_marker not in completed.stdout or status_marker not in completed.stdout:
            return OpsApiResponse(
                endpoint=normalized_endpoint,
                status=0,
                body=f"ssh curl command returned unexpected output: {completed.stdout.strip()}",
                payload=payload,
            )

        response_output, curl_exit = completed.stdout.rsplit(exit_marker, maxsplit=1)
        body, http_status = response_output.rsplit(status_marker, maxsplit=1)
        curl_exit_code = int(curl_exit.strip().splitlines()[0])
        if curl_exit_code != 0:
            stderr = completed.stderr.strip()
            return OpsApiResponse(
                endpoint=normalized_endpoint,
                status=0,
                body=f"curl failed with exit {curl_exit_code}: {stderr or body.strip()}",
                payload=payload,
            )

        return OpsApiResponse(
            endpoint=normalized_endpoint,
            status=int(http_status.strip().splitlines()[0]),
            body=body.strip(),
            payload=payload,
        )

    def _append_ops_log(
        self,
        *,
        method: str,
        endpoint: str,
        payload: dict[str, Any],
        authenticated: bool,
        status: int,
        body: str,
    ) -> Path:
        log_path = get_settings().ops_api_log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as file:
            file.write(f"[{datetime.now(timezone.utc).isoformat()}]\n")
            file.write(f"method: {method}\n")
            file.write(f"endpoint: /{endpoint.lstrip('/')}\n")
            file.write(f"execution_mode: {self.execution_mode}\n")
            file.write(f"authenticated: {authenticated}\n")
            file.write(f"status: {status}\n")
            file.write("payload:\n")
            file.write(json.dumps(payload, indent=2, sort_keys=True))
            file.write("\n")
            file.write("output:\n")
            file.write(body.rstrip())
            file.write("\n")
            file.write("=" * 80)
            file.write("\n")
        return log_path


def normalize_symbol(symbol: str, quote_ccy: str = "USDT") -> str:
    normalized = symbol.strip().upper().replace("_", "-")
    if not normalized:
        raise ValueError("Symbol cannot be empty.")
    if "-" not in normalized:
        normalized = f"{normalized}-{quote_ccy.strip().upper()}"
    return normalized


def base_from_symbol(symbol: str, quote_ccy: str = "USDT") -> str:
    return normalize_symbol(symbol, quote_ccy).split("-", maxsplit=1)[0]
