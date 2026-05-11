from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request
from ops_bot.settings import app_settings

class SignalClient:
    def __init__(self, sender: str | None = None, base_url: str | None = None) -> None:
        self.sender = sender or app_settings.signal_sender
        resolved_base_url = base_url or app_settings.signal_base_url
        self.base_url = resolved_base_url.rstrip("/")

    def send(
        self,
        message: str | Path | list[str | Path] | tuple[str | Path, ...],
        *,
        attachments: str | Path | list[str | Path] | tuple[str | Path, ...] | None = None,
        recipient: str | None = None,
        group_id: str | None = None,
    ) -> dict[str, Any]:
        recipients = self._resolve_recipients(recipient=recipient, group_id=group_id)
        text, encoded_attachments = self._normalize_message(message, attachments=attachments)

        payload: dict[str, Any] = {
            "message": text,
            "number": self.sender,
            "recipients": recipients,
        }
        if encoded_attachments:
            payload["base64_attachments"] = encoded_attachments

        return self._post("/v2/send", payload)

    def _resolve_recipients(
        self,
        *,
        recipient: str | None,
        group_id: str | None,
    ) -> list[str]:
        # prioritize recipient if both are provided, but allow both to be sent if desired by caller
        # if bool(recipient) == bool(group_id):
        #     raise ValueError("Pass exactly one of recipient or group_id.")
        if recipient:
            return [recipient]

        assert group_id is not None
        if group_id.startswith("https://signal.group/#"):
            raise ValueError(
                "group_id must be the API group id from GET /v1/groups/{number}, not a Signal invite link."
            )
        if not group_id.startswith("group."):
            raise ValueError(
                "group_id must start with 'group.' and come from GET /v1/groups/{number}."
            )
        return [group_id]

    def _normalize_message(
        self,
        message: str | Path | list[str | Path] | tuple[str | Path, ...],
        *,
        attachments: str | Path | list[str | Path] | tuple[str | Path, ...] | None = None,
    ) -> tuple[str, list[str]]:
        encoded_attachments = self._normalize_attachments(attachments)

        if isinstance(message, Path):
            return "", [self._encode_file(message), *encoded_attachments]

        if isinstance(message, str):
            path = Path(message)
            if path.exists() and path.is_file():
                return "", [self._encode_file(path), *encoded_attachments]
            return message, encoded_attachments

        if isinstance(message, (list, tuple)):
            if not message:
                raise ValueError("message list cannot be empty.")
            list_attachments = [self._encode_file(Path(item)) for item in message]
            return "", [*list_attachments, *encoded_attachments]

        raise TypeError("message must be text, a file path, or a list of file paths.")

    def _normalize_attachments(
        self,
        attachments: str | Path | list[str | Path] | tuple[str | Path, ...] | None,
    ) -> list[str]:
        if attachments is None:
            return []

        if isinstance(attachments, Path):
            return [self._encode_file(attachments)]

        if isinstance(attachments, str):
            return [self._encode_file(Path(attachments))]

        if isinstance(attachments, (list, tuple)):
            if not attachments:
                raise ValueError("attachments list cannot be empty.")
            return [self._encode_file(Path(item)) for item in attachments]

        raise TypeError("attachments must be a file path or a list of file paths.")

    def _encode_file(self, file_path: Path) -> str:
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"Attachment not found: {file_path}")
        return base64.b64encode(file_path.read_bytes()).decode("utf-8")

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=f"{self.base_url}{endpoint}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Signal API HTTP {exc.code}: {error_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Signal API request failed: {exc.reason}") from exc

        if not raw:
            return {"success": True}
        return json.loads(raw)
