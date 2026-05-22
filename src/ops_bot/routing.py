from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AgentName = Literal[
    "help",
    "health",
    "balance",
    "transfer",
    "monitor",
    "volume_fills",
    "stacker_status",
    "new_listing",
    "setup_stackers",
    "schedule_prefect",
]


@dataclass(frozen=True)
class RoutedMessage:
    agent: AgentName
    question: str
    command: str | None = None


COMMAND_HELP: tuple[str, ...] = (
    "/help -> list bot commands",
    "/health, /ping -> API health check",
    "/balance, /bal -> get balance",
    "/transfer, /move, /withdraw -> run transfer",
    "/monitor, /watch -> run monitor",
    "/volume-fills -> get volume strategy fills",
    "/stacker-status -> check stacker accepted orders",
    "/new-listing -> create config and run new-listing workflow",
    "/new-listing-dryrun -> create config and run dry-run preview",
    "/setup-stackers -> create and save stacker request body",
    "/setup-stackers-dryrun -> create and save dry-run stacker request body",
    "/schedule-volume -> create one Prefect run for volume-start-strategy",
    "/schedule-mirror -> create one Prefect run for mirror-control",
    "/schedule-stackers -> create 4 Prefect runs for stacker levels 1 to 4 with configurable interval minutes",
    "/schedule-new-listing -> create stackers 1-4, then volume, then mirror from one start time",
    "/remove-schedules -> delete Prefect flow runs by flow_run_id or flow_run_ids",
)

COMMAND_ALIASES: dict[str, AgentName] = {
    "/help": "help",
    "/health": "health",
    "/ping": "health",
    "/balance": "balance",
    "/bal": "balance",
    "/transfer": "transfer",
    "/move": "transfer",
    "/withdraw": "transfer",
    "/monitor": "monitor",
    "/watch": "monitor",
    "/volume-fills": "volume_fills",
    "/stackers-status": "stacker_status",
    "/new-listing": "new_listing",
    "/new-listing-dryrun": "new_listing",
    "/setup-stackers": "setup_stackers",
    "/setup-stackers-dryrun": "setup_stackers",
    "/setup-stacker-config": "setup_stackers",
    "/schedule-volume": "schedule_prefect",
    "/schedule-mirror": "schedule_prefect",
    "/schedule-stacker": "schedule_prefect",
    "/schedule-new-listing": "schedule_prefect",
    "/remove-schedules": "schedule_prefect",
}

NEW_LISTING_DRYRUN_COMMANDS = frozenset({"/new-listing-dryrun"})
NEW_LISTING_TEMPLATE_COMMANDS = frozenset({"/new-listing", *NEW_LISTING_DRYRUN_COMMANDS})
SETUP_STACKERS_DRYRUN_COMMANDS = frozenset({"/setup-stackers-dryrun"})
SETUP_STACKERS_TEMPLATE_COMMANDS = frozenset(
    {"/setup-stackers", "/setup-stacker-config", *SETUP_STACKERS_DRYRUN_COMMANDS}
)
PREFECT_SCHEDULE_TEMPLATE_COMMANDS = frozenset(
    {
        "/schedule-volume",
        "/schedule-mirror",
        "/schedule-stacker",
        "/schedule-new-listing",
        "/remove-schedules",
    }
)


def route_message(text: str) -> RoutedMessage | None:
    stripped = text.strip()
    if not stripped:
        return None

    parts = stripped.split(maxsplit=1)
    command = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""
    if command in COMMAND_ALIASES:
        return RoutedMessage(
            agent=COMMAND_ALIASES[command],
            question=rest.strip() or stripped,
            command=command,
        )
    if command.startswith("/"):
        return None

    lower = stripped.lower()
    if any(phrase in lower for phrase in ("server up", "health", "ping api", "ping the api")):
        return RoutedMessage(agent="health", question=stripped)

    if any(phrase in lower for phrase in ("balance", "how much", "available", "wallet")):
        return RoutedMessage(agent="balance", question=stripped)

    if any(
        phrase in lower
        for phrase in (
            "transfer",
            "move funds",
            "withdraw",
            "sub to main",
            "main to sub",
            "future to spot",
            "spot to future",
            "trading to funding",
        )
    ):
        return RoutedMessage(agent="transfer", question=stripped)

    if any(phrase in lower for phrase in ("monitor", "watch positions", "show strategy", "stream monitor")):
        return RoutedMessage(agent="monitor", question=stripped)

    if any(
        phrase in lower
        for phrase in ("volume fills", "strategy fills", "volume-fills")
    ):
        return RoutedMessage(agent="volume_fills", question=stripped)

    if any(
        phrase in lower
        for phrase in (
            "stacker status",
            "stacker-status",
            "accepted orders",
            "check status",
        )
    ):
        return RoutedMessage(agent="stacker_status", question=stripped)

    if any(
        phrase in lower for phrase in ("new listing", "new-listing", "newlisting")
    ):
        return RoutedMessage(agent="new_listing", question=stripped)

    if any(
        phrase in lower
        for phrase in ("setup stackers", "setup stacker config", "stacker config")
    ):
        return RoutedMessage(agent="setup_stackers", question=stripped)

    if any(phrase in lower for phrase in ("help", "commands", "what can you do")):
        return RoutedMessage(agent="help", question=stripped)

    return None
