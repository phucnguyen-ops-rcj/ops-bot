from __future__ import annotations

from ops_bot.clients.ops_api import OpsApiClient
from ops_bot.extractor import extract_params
from ops_bot.new_listing import (
    NEW_LISTING_INPUT_TEMPLATE,
    handle_new_listing_command,
)
from ops_bot.ops_requests import OpsCall, build_ops_call
from ops_bot.prefect_schedules import (
    handle_schedule_prefect_command,
    schedule_template_for_command,
)
from ops_bot.response_format import format_ops_response_body
from ops_bot.responses import BotResponse
from ops_bot.stackers import (
    SETUP_STACKERS_INPUT_TEMPLATE,
    handle_setup_stackers_command,
)
from ops_bot.routing import (
    COMMAND_HELP,
    NEW_LISTING_DRYRUN_COMMANDS,
    NEW_LISTING_TEMPLATE_COMMANDS,
    PREFECT_SCHEDULE_TEMPLATE_COMMANDS,
    SETUP_STACKERS_DRYRUN_COMMANDS,
    SETUP_STACKERS_TEMPLATE_COMMANDS,
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

    if routed.agent == "setup_stackers" and routed.command in SETUP_STACKERS_TEMPLATE_COMMANDS and routed.question.strip() in {"", routed.command}:
        return SETUP_STACKERS_INPUT_TEMPLATE

    if routed.agent == "schedule_prefect" and routed.command in PREFECT_SCHEDULE_TEMPLATE_COMMANDS and routed.question.strip() in {"", routed.command}:
        return schedule_template_for_command(routed.command)

    if routed.agent == "setup_stackers":
        try:
            return handle_setup_stackers_command(
                routed.question,
                dry_run=routed.command in SETUP_STACKERS_DRYRUN_COMMANDS,
            )
        except ValueError as exc:
            return str(exc)

    if routed.agent == "schedule_prefect":
        try:
            return handle_schedule_prefect_command(
                routed.question,
                command=routed.command,
            )
        except ValueError as exc:
            return str(exc)

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
    return format_ops_response_body(call.endpoint, body)
