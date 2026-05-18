from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import urllib.error
import urllib.request
from typing import Any

import websocket

from ops_bot.clients.signal import SignalClient
from ops_bot.responses import BotResponse
from ops_bot.service import handle_user_message
from ops_bot.settings import app_settings
from ops_bot.signal_groups import SignalGroupIdCache

logger = logging.getLogger(__name__)


def _extract_data_message(payload: dict[str, Any]) -> dict[str, Any]:
    data_message = payload.get("envelope", {}).get("dataMessage") or {}
    return data_message if isinstance(data_message, dict) else {}


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
    data_message = _extract_data_message(payload)
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
    data_message = _extract_data_message(payload)
    if _is_group_message(data_message):
        group_id = _extract_sendable_group_id(data_message)
        if group_id:
            return {"recipient": None, "group_id": group_id}
        logger.warning(
            "Group message did not include a sendable group id. Set "
            "SIGNAL_GROUP_ID from GET /v1/groups/%s.",
            app_settings.signal_sender,
        )
        return {"recipient": None, "group_id": None}
    return {"recipient": _extract_source(payload), "group_id": None}


def _is_group_message(data_message: dict[str, Any]) -> bool:
    for key in ("group", "groupInfo", "groupV2"):
        group = data_message.get(key)
        if isinstance(group, dict) and group:
            return True
    return False


def _extract_sendable_group_id(data_message: dict[str, Any]) -> str | None:
    receive_group_ids = _extract_receive_group_ids(data_message)
    for group_id in receive_group_ids:
        if _is_sendable_group_id(group_id):
            return group_id

    cache = SignalGroupIdCache(app_settings.signal_group_cache_path)
    cached_group_id = cache.lookup(receive_group_ids)
    if cached_group_id:
        return cached_group_id

    if receive_group_ids:
        try:
            cache.update_from_groups(SignalClient().list_groups())
        except Exception as exc:
            logger.warning("Failed to refresh Signal group id cache: %s", exc)
        cached_group_id = cache.lookup(receive_group_ids)
        if cached_group_id:
            return cached_group_id

    configured_group_id = app_settings.signal_group_id.strip()
    if _is_sendable_group_id(configured_group_id):
        return configured_group_id
    return None


def _extract_receive_group_ids(data_message: dict[str, Any]) -> list[str]:
    receive_group_ids: list[str] = []
    for key in ("group", "groupInfo", "groupV2"):
        group = data_message.get(key)
        if not isinstance(group, dict):
            continue
        for id_key in ("id", "groupId", "internal_id", "internalId", "masterKey"):
            group_id = group.get(id_key)
            if isinstance(group_id, str) and group_id.strip():
                receive_group_ids.append(group_id.strip())
    return _unique(receive_group_ids)


def _is_sendable_group_id(group_id: object) -> bool:
    return isinstance(group_id, str) and group_id.strip().startswith("group.")


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def _configured_mention_aliases() -> list[str]:
    aliases = [
        alias.strip()
        for alias in app_settings.signal_bot_mention_aliases.split(",")
        if alias.strip()
    ]
    if app_settings.signal_sender:
        aliases.append(app_settings.signal_sender)

    expanded: list[str] = []
    for alias in aliases:
        expanded.append(alias)
        if not alias.startswith("@") and not alias.startswith("+"):
            expanded.append(f"@{alias}")
    return sorted(set(expanded), key=len, reverse=True)


def _normalise_identifier(value: object) -> str:
    return str(value).strip().lower().replace(" ", "")


def _mentions_bot_by_metadata(data_message: dict[str, Any]) -> bool:
    mentions = data_message.get("mentions") or data_message.get("messageMentions")
    if not isinstance(mentions, list):
        return False

    bot_ids = {
        _normalise_identifier(identifier)
        for identifier in _configured_mention_aliases()
    }
    for mention in mentions:
        if isinstance(mention, dict):
            values = mention.values()
        else:
            values = [mention]
        if any(_normalise_identifier(value) in bot_ids for value in values):
            return True
    return False


def _alias_pattern(alias: str) -> re.Pattern[str]:
    escaped = re.escape(alias)
    if alias.startswith("@"):
        pattern = rf"(?<!\S){escaped}(?=$|\s|[:,])"
    else:
        pattern = rf"(?<![\w@]){escaped}(?=$|[^\w])"
    return re.compile(pattern, re.IGNORECASE)


def _mentions_bot_by_text(text: str) -> bool:
    return any(
        _alias_pattern(alias).search(text)
        for alias in _configured_mention_aliases()
    )


def _strip_bot_mentions(text: str) -> str:
    stripped = text.replace("\ufffc", " ")
    for alias in _configured_mention_aliases():
        stripped = _alias_pattern(alias).sub(" ", stripped)
    return " ".join(stripped.split())


def _text_for_handling(payload: dict[str, Any]) -> str | None:
    text = _extract_text(payload)
    if not text:
        return None

    data_message = _extract_data_message(payload)
    if not _is_group_message(data_message):
        return text

    if not (
        _mentions_bot_by_metadata(data_message)
        or _mentions_bot_by_text(text)
    ):
        logger.info(
            "Ignoring unmentioned group message from %s.",
            _extract_source(payload),
        )
        return None

    return _strip_bot_mentions(text) or None


def _send_reply(message: str | BotResponse, payload: dict[str, Any]) -> None:
    target = _reply_target(payload)
    if not target["recipient"] and not target["group_id"]:
        logger.warning(
            "Skipping reply because no Signal recipient or group id was found."
        )
        return
    text = message.message if isinstance(message, BotResponse) else message
    attachments = message.attachments if isinstance(message, BotResponse) else None
    SignalClient().send(
        text,
        attachments=attachments,
        recipient=target["recipient"],
        group_id=target["group_id"],
    )


def _handle_payload(payload: dict[str, Any]) -> None:
    text = _text_for_handling(payload)
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
