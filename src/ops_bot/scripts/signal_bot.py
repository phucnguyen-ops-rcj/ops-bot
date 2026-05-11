from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

import websocket

from ops_bot.clients.signal import SignalClient
from ops_bot.service import handle_user_message
from ops_bot.settings import app_settings

logger = logging.getLogger(__name__)


def _receive_url() -> str:
    base_url = app_settings.signal_base_url.rstrip("/")
    if base_url.startswith("https://"):
        ws_base = "wss://" + base_url.removeprefix("https://")
    else:
        ws_base = "ws://" + base_url.removeprefix("http://")
    return f"{ws_base}/v1/receive/{app_settings.signal_sender}"


def _poll_url() -> str:
    return (
        f"{app_settings.signal_base_url.rstrip('/')}/v1/receive/"
        f"{app_settings.signal_sender}"
    )


def _extract_text(payload: dict[str, Any]) -> str | None:
    data_message = payload.get("envelope", {}).get("dataMessage") or {}
    text = (
        data_message.get("message")
        or data_message.get("body")
        or data_message.get("summary")
    )
    return str(text).strip() if text else None


def _extract_source(payload: dict[str, Any]) -> str | None:
    source = payload.get("envelope", {}).get("source")
    return str(source).strip() if source else None


def _reply_target(payload: dict[str, Any]) -> dict[str, str | None]:
    data_message = payload.get("envelope", {}).get("dataMessage") or {}
    group_id = _extract_group_id(data_message)
    if group_id:
        return {"recipient": None, "group_id": group_id}
    return {"recipient": _extract_source(payload), "group_id": None}


def _extract_group_id(data_message: dict[str, Any]) -> str | None:
    for key in ("group", "groupInfo", "groupV2"):
        group = data_message.get(key)
        if not isinstance(group, dict):
            continue
        for id_key in ("id", "groupId", "masterKey"):
            group_id = group.get(id_key)
            if group_id:
                return str(group_id)
    return None


def _send_reply(message: str, payload: dict[str, Any]) -> None:
    target = _reply_target(payload)
    if not target["recipient"] and not target["group_id"]:
        logger.warning(
            "Skipping reply because no Signal recipient or group id was found."
        )
        return
    SignalClient().send(
        message,
        recipient=target["recipient"],
        group_id=target["group_id"],
    )


def _handle_payload(payload: dict[str, Any]) -> None:
    text = _extract_text(payload)
    if not text:
        return

    logger.info("Received Signal message from %s: %s", _extract_source(payload), text)
    try:
        response = asyncio.run(handle_user_message(text))
    except Exception as exc:
        logger.error("Failed to handle Signal message: %s", exc, exc_info=True)
        response = f"Bot error: {exc}"

    if response is None:
        return

    try:
        _send_reply(response, payload)
    except Exception as exc:
        logger.error("Failed to send Signal bot response: %s", exc, exc_info=True)


def _iter_payloads(raw_payload: Any) -> list[dict[str, Any]]:
    if isinstance(raw_payload, list):
        return [item for item in raw_payload if isinstance(item, dict)]
    if isinstance(raw_payload, dict):
        return [raw_payload]
    return []


def _handle_ws_message(raw_message: str | bytes) -> None:
    if isinstance(raw_message, bytes):
        raw_message = raw_message.decode("utf-8", errors="replace")
    for payload in _iter_payloads(json.loads(raw_message)):
        _handle_payload(payload)


def _poll_once() -> list[dict[str, Any]]:
    request = urllib.request.Request(_poll_url(), method="GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8", errors="replace")
    if not raw.strip():
        return []
    return _iter_payloads(json.loads(raw))


def _run_poll_forever(initial_payloads: list[dict[str, Any]] | None = None) -> None:
    logger.info("Polling Signal receive endpoint: %s", _poll_url())
    for payload in initial_payloads or []:
        _handle_payload(payload)

    while True:
        try:
            for payload in _poll_once():
                _handle_payload(payload)
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            logger.error("Signal polling failed: %s", exc, exc_info=True)
        time.sleep(app_settings.signal_bot_poll_seconds)


def _run_websocket_forever() -> None:
    receive_url = _receive_url()
    logger.info("Connecting to Signal receive WebSocket: %s", receive_url)
    ws = websocket.WebSocketApp(
        receive_url,
        on_message=lambda _ws, message: _handle_ws_message(message),
        on_error=lambda _ws, error: logger.error("Signal WebSocket error: %s", error),
        on_close=lambda _ws, code, reason: logger.warning(
            "Signal WebSocket closed: code=%s reason=%s", code, reason
        ),
        on_open=lambda _ws: logger.info("Signal bot connected."),
    )
    ws.run_forever()


def _detect_polling_receive() -> list[dict[str, Any]] | None:
    try:
        return _poll_once()
    except Exception as exc:
        logger.info("Signal receive endpoint did not behave as HTTP polling: %s", exc)
        return None


def run_forever() -> None:
    mode = app_settings.signal_bot_receive_mode
    if mode == "poll":
        _run_poll_forever()
        return

    if mode == "auto":
        initial_payloads = _detect_polling_receive()
        if initial_payloads is not None:
            logger.info("Detected HTTP polling receive mode.")
            _run_poll_forever(initial_payloads)
            return

    while True:
        _run_websocket_forever()
        time.sleep(5)


def main() -> None:
    logging.basicConfig(
        level=app_settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_forever()


if __name__ == "__main__":
    main()
