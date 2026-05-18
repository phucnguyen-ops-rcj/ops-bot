from __future__ import annotations

import json

from ops_bot.clients.ops_api import OpsApiClient
from ops_bot.extractor import extract_params
from ops_bot.new_listing import (
    NEW_LISTING_INPUT_TEMPLATE,
    handle_new_listing_command,
)
from ops_bot.ops_requests import OpsCall, build_ops_call
from ops_bot.responses import BotResponse
from ops_bot.routing import (
    COMMAND_HELP,
    NEW_LISTING_DRYRUN_COMMANDS,
    NEW_LISTING_TEMPLATE_COMMANDS,
    route_message,
)

HELP_TEXT = "\n".join(["Available commands:", *COMMAND_HELP])


async def handle_user_message(
    text: str,
    *,
    client: OpsApiClient | None = None,
    execute: bool = True,
) -> str | BotResponse | None:
    routed = route_message(text)
    if routed is None:
        return None

    if routed.agent == "help":
        return HELP_TEXT

    if routed.agent == "new_listing" and routed.command in NEW_LISTING_TEMPLATE_COMMANDS and routed.question.strip() in {"", routed.command}:
        return NEW_LISTING_INPUT_TEMPLATE

    extracted = await extract_params(routed.agent, routed.question)
    missing_fields = [field for field in extracted.get("missing_fields", []) if field]
    if missing_fields:
        return f"Missing required field(s): {', '.join(missing_fields)}"

    if routed.agent == "new_listing":
        try:
            return handle_new_listing_command(
                extracted,
                dry_run=routed.command in NEW_LISTING_DRYRUN_COMMANDS,
            )
        except ValueError as exc:
            return str(exc)

    try:
        call = build_ops_call(routed.agent, extracted)
    except ValueError as exc:
        return str(exc)

    if not execute:
        return _format_dry_run(call)

    ops_client = client or OpsApiClient()
    response = ops_client.request(
        method=call.method,
        endpoint=call.endpoint,
        payload=call.payload,
        authenticated=call.authenticated,
    )
    return _format_response(call, response.status, response.body)


def _format_dry_run(call: OpsCall) -> str:
    return "\n".join(
        [
            "Dry run:",
            f"{call.method} {call.endpoint}",
            json.dumps(call.payload, indent=2, sort_keys=True),
        ]
    )


def _format_response(call: OpsCall, status: int, body: str) -> str:
    payload = _extract_json_payload(body)
    if isinstance(payload, dict):
        if call.endpoint == "/get-balance":
            payload = _compact_balance_payload(payload)
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    cleaned_body = body.rstrip()
    return cleaned_body or "<empty response>"


def _extract_json_payload(body: str) -> dict | list | None:
    decoder = json.JSONDecoder()
    latest_payload: dict | list | None = None
    for index, char in enumerate(body):
        if char not in "[{":
            continue
        try:
            payload, _ = decoder.raw_decode(body[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, (dict, list)):
            latest_payload = payload
    return latest_payload


def _compact_balance_payload(payload: dict) -> dict:
    keys = ("account", "balance", "exchange", "token")
    compact = {key: payload[key] for key in keys if key in payload}
    return compact or payload
