from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
DEFAULT_DATA_ROOT = Path("/data") if Path("/data").exists() else Path(".docker-data")


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
    signal_group_id: str = Field(default="")
    signal_bot_receive_mode: Literal["auto", "websocket", "poll"] = Field(
        default="auto"
    )
    signal_bot_mention_aliases: str = Field(default="opsbot,@opsbot")
    signal_bot_poll_seconds: float = Field(default=2.0)

    # OPENAI
    openai_api_key: str

    # RCJ ops API
    rcj_ops_bearer_token: str
    rcj_ops_base_endpoint: str = Field(default="http://18.176.93.228")
    rcj_ops_timeout_seconds: int = Field(default=60)
    rcj_ops_execution_mode: Literal["ssh", "local"] = Field(default="ssh")
    rcj_ops_ssh_host: str = Field(default="T1_newuser1")
    ops_api_log_path: Path = Field(default=DEFAULT_DATA_ROOT / "ops_api.log")

    # New listing
    new_listing_config_dir: Path = Field(
        default=DEFAULT_DATA_ROOT / "new_listing/config"
    )
    new_listing_logs_dir: Path = Field(default=DEFAULT_DATA_ROOT / "new_listing/logs")
    new_listing_gateway_symbols_path: Path = Field(
        default=DEFAULT_DATA_ROOT / "new_listing/gateway_symbols.yml"
    )
    new_listing_trading_volume_path: Path = Field(
        default=DEFAULT_DATA_ROOT / "trading_volume.json"
    )
    new_listing_account_id: str = Field(default="ktfsmc15")
    stacker_config_dir: Path = Field(default=DEFAULT_DATA_ROOT / "stackers/config")
    stacker_logs_dir: Path = Field(default=DEFAULT_DATA_ROOT / "stackers/logs")
    prefect_api_url: str = Field(default="")
    prefect_api_auth_string: str = Field(default="")
    prefect_ui_url: str = Field(default="")
    prefect_timeout_seconds: int = Field(default=30)
    prefect_timezone: str = Field(default="Asia/Singapore")
    prefect_schedule_logs_dir: Path = Field(
        default=DEFAULT_DATA_ROOT / "prefect_schedules/logs"
    )
    prefect_schedule_state_dir: Path = Field(
        default=DEFAULT_DATA_ROOT / "prefect_schedules/state"
    )

    # Logging
    log_level: str = Field(default="INFO")

    @field_validator(
        "signal_base_url",
        "signal_sender",
        "signal_bot_receive_mode",
        "signal_bot_mention_aliases",
        "signal_bot_poll_seconds",
        "openai_api_key",
        "rcj_ops_bearer_token",
        "rcj_ops_base_endpoint",
        "rcj_ops_timeout_seconds",
        "rcj_ops_execution_mode",
        "rcj_ops_ssh_host",
        "new_listing_account_id",
        "signal_group_id",
        "log_level",
        "prefect_api_url",
        "prefect_api_auth_string",
        "prefect_ui_url",
        "prefect_timeout_seconds",
        "prefect_timezone",
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

    @field_validator(
        "new_listing_config_dir",
        "new_listing_logs_dir",
        "new_listing_gateway_symbols_path",
        "new_listing_trading_volume_path",
        "stacker_config_dir",
        "stacker_logs_dir",
        "ops_api_log_path",
        "prefect_schedule_logs_dir",
        "prefect_schedule_state_dir",
        mode="before",
    )
    @classmethod
    def strip_new_listing_path_env_quotes(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return Path(_strip_outer_quotes(value))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


app_settings = get_settings()
