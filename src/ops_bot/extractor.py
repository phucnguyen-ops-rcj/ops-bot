from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from baml_py import ClientRegistry

from .routing import AgentName
from .settings import get_settings


async def extract_params(agent: AgentName, user_question: str) -> dict[str, Any]:
    baml_options = _baml_options()
    try:
        from baml_client.async_client import b
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "BAML client is not generated. Run `uv run baml-cli generate` first."
        ) from exc

    if agent == "health":
        result = await b.ExtractHealthRequest(user_question, baml_options)
    elif agent == "balance":
        result = await b.ExtractBalanceRequest(user_question, baml_options)
    elif agent == "transfer":
        result = await b.ExtractTransferRequest(user_question, baml_options)
    elif agent == "monitor":
        result = await b.ExtractMonitorRequest(user_question, baml_options)
    elif agent == "volume_fills":
        result = await b.ExtractVolumeFillsRequest(user_question, baml_options)
    elif agent == "stacker_status":
        result = await b.ExtractStackerStatusRequest(user_question, baml_options)
    else:
        raise ValueError(f"Unsupported agent: {agent}")

    return _to_dict(result)


def _baml_options() -> dict[str, ClientRegistry]:
    openai_api_key = get_settings().openai_api_key.strip()
    if not openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    client_registry = ClientRegistry()
    client_registry.add_llm_client(
        name="SettingsOpsExtractor",
        provider="openai",
        options={
            "model": "gpt-5-mini",
            "api_key": openai_api_key,
        },
    )
    client_registry.set_primary("SettingsOpsExtractor")
    return {"client_registry": client_registry}


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
