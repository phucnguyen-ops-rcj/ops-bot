from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def _strip_outer_quotes(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return stripped


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Signal messaging
    signal_base_url: str = Field(default="http://127.0.0.1:8081")
    signal_sender: str
    signal_group_cache_path: Path = Field(default=Path("signal_groups.yml"))
    signal_bot_receive_mode: Literal["auto", "websocket", "poll"] = Field(
        default="auto"
    )
    signal_bot_poll_seconds: float = Field(default=2.0)

    # OPENAI
    openai_api_key: str

    # RCJ ops API
    rcj_ops_bearer_token: str
    rcj_ops_base_endpoint: str = Field(default="http://18.176.93.228")
    rcj_ops_timeout_seconds: int = Field(default=60)
    rcj_ops_execution_mode: Literal["ssh", "local"] = Field(default="ssh")
    rcj_ops_ssh_host: str = Field(default="T1_newuser1")

    # Logging
    log_level: str = Field(default="INFO")

    @field_validator(
        "signal_base_url",
        "signal_sender",
        "signal_bot_receive_mode",
        "signal_bot_poll_seconds",
        "openai_api_key",
        "rcj_ops_bearer_token",
        "rcj_ops_base_endpoint",
        "rcj_ops_timeout_seconds",
        "rcj_ops_execution_mode",
        "rcj_ops_ssh_host",
        "log_level",
        mode="before",
    )
    @classmethod
    def strip_env_quotes(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return _strip_outer_quotes(value)

    @field_validator("signal_group_cache_path", mode="before")
    @classmethod
    def strip_path_env_quotes(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return Path(_strip_outer_quotes(value))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


app_settings = get_settings()
