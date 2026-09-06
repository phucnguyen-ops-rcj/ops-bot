from __future__ import annotations

from pathlib import Path

import pytest

from ops_bot.prefect_schedules.bot_service import PrefectApiClient
from ops_bot.settings import DEFAULT_DATA_ROOT, Settings


def test_settings_strip_docker_env_file_quotes() -> None:
    settings = Settings(
        signal_sender='"+84559854979"',
        signal_base_url='"http://host.docker.internal:8081"',
        signal_bot_receive_mode='"auto"',
        signal_bot_mention_aliases='"opsbot,@opsbot"',
        signal_bot_poll_seconds='"2"',
        openai_api_key='"sk-test"',
        rcj_ops_timeout_seconds='"60"',
        signal_group_cache_path='"/data/signal_groups.yml"',
    )

    assert settings.signal_sender == "+84559854979"
    assert settings.signal_base_url == "http://host.docker.internal:8081"
    assert settings.signal_bot_receive_mode == "auto"
    assert settings.signal_bot_mention_aliases == "opsbot,@opsbot"
    assert settings.signal_bot_poll_seconds == 2
    assert settings.openai_api_key == "sk-test"
    assert settings.rcj_ops_timeout_seconds == 60
    assert settings.signal_group_cache_path == Path("/data/signal_groups.yml")


def test_new_listing_paths_default_to_shared_data_root() -> None:
    settings = Settings(
        signal_sender="+84559854979",
        openai_api_key="sk-test",
        rcj_ops_bearer_token="token",
    )

    assert settings.new_listing_config_dir == DEFAULT_DATA_ROOT / "new_listing/config"
    assert settings.new_listing_logs_dir == DEFAULT_DATA_ROOT / "new_listing/logs"
    assert settings.new_listing_gateway_symbols_path == (
        DEFAULT_DATA_ROOT / "new_listing/gateway_symbols.yml"
    )
    assert settings.new_listing_trading_volume_path == DEFAULT_DATA_ROOT / "trading_volume.json"
    assert settings.ops_api_log_path == DEFAULT_DATA_ROOT / "ops_api.log"
    assert settings.stacker_config_dir == DEFAULT_DATA_ROOT / "stackers/config"
    assert settings.stacker_logs_dir == DEFAULT_DATA_ROOT / "stackers/logs"
    assert settings.prefect_api_url == ""
    assert settings.prefect_ui_url == ""
    assert settings.prefect_timeout_seconds == 30
    assert settings.prefect_timezone == "Asia/Singapore"
    assert settings.prefect_schedule_logs_dir == DEFAULT_DATA_ROOT / "prefect_schedules/logs"
    assert settings.prefect_schedule_state_dir == DEFAULT_DATA_ROOT / "prefect_schedules/state"


def test_prefect_urls_are_loaded_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("PREFECT_API_URL", "http://prefect.internal:4200/api")
    monkeypatch.setenv("PREFECT_API_AUTH_STRING", "admin:test-password")
    monkeypatch.setenv("PREFECT_UI_URL", "http://prefect.example:4200")

    settings = Settings(
        signal_sender="+84559854979",
        openai_api_key="sk-test",
        rcj_ops_bearer_token="token",
    )

    assert settings.prefect_api_url == "http://prefect.internal:4200/api"
    assert settings.prefect_api_auth_string == "admin:test-password"
    assert settings.prefect_ui_url == "http://prefect.example:4200"


def test_prefect_client_requires_api_url() -> None:
    with pytest.raises(ValueError, match="PREFECT_API_URL is not set"):
        PrefectApiClient(api_url="")


def test_prefect_client_validates_auth_string() -> None:
    with pytest.raises(ValueError, match="username:password format"):
        PrefectApiClient(
            api_url="http://prefect.test:4200/api",
            auth_string="invalid",
        )
