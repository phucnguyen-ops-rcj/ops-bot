from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from .routing import AgentName


async def extract_params(agent: AgentName, user_question: str) -> dict[str, Any]:
    try:
        from baml_client.async_client import b
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "BAML client is not generated. Run `uv run baml-cli generate` first."
        ) from exc

    if agent == "health":
        result = await b.ExtractHealthRequest(user_question)
    elif agent == "balance":
        result = await b.ExtractBalanceRequest(user_question)
    elif agent == "transfer":
        result = await b.ExtractTransferRequest(user_question)
    elif agent == "monitor":
        result = await b.ExtractMonitorRequest(user_question)
    else:
        raise ValueError(f"Unsupported agent: {agent}")

    return _to_dict(result)


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    raise TypeError(f"Cannot convert BAML result to dict: {type(value)!r}")

