from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AgentName = Literal[
    "health",
    "balance",
    "transfer",
    "monitor",
    "volume_fills",
    "stacker_status",
]


@dataclass(frozen=True)
class RoutedMessage:
    agent: AgentName
    question: str
    command: str | None = None


COMMAND_ALIASES: dict[str, AgentName] = {
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
    "/stacker-status": "stacker_status",
}


def route_message(text: str) -> RoutedMessage | None:
    stripped = text.strip()
    if not stripped:
        return None

    first, _, rest = stripped.partition(" ")
    command = first.lower()
    if command in COMMAND_ALIASES:
        return RoutedMessage(
            agent=COMMAND_ALIASES[command],
            question=rest.strip() or stripped,
            command=command,
        )

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

    return None
