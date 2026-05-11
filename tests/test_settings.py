from __future__ import annotations

from pathlib import Path

from ops_bot.settings import Settings


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
