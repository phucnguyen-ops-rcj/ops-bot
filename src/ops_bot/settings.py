from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Signal messaging
    signal_base_url: str = Field(default="http://127.0.0.1:8081")
    signal_sender: str
    signal_recipient: str | None = Field(default=None)
    signal_group_id: str = Field(default="")
    signal_bot_receive_mode: Literal["auto", "websocket", "poll"] = Field(
        default="auto"
    )
    signal_bot_poll_seconds: float = Field(default=2.0)

    # RCJ ops API
    rcj_ops_bearer_token: str = Field(
        default_factory=lambda: os.environ.get("RCJ_OPS_BEARER_TOKEN", "")
    )
    rcj_ops_base_endpoint: str = Field(default="http://18.176.93.228")
    rcj_ops_timeout_seconds: int = Field(default=60)
    rcj_ops_execution_mode: Literal["ssh", "local"] = Field(default="ssh")
    rcj_ops_ssh_host: str = Field(default="T1_newuser1")

    # Logging
    log_level: str = Field(default="INFO")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


app_settings = get_settings()
