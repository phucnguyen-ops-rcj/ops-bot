from __future__ import annotations

import asyncio
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from ops_bot.new_listing.bot_service import (
    NEW_LISTING_INPUT_TEMPLATE,
    NewListingRequest,
    build_new_listing_config,
    handle_new_listing_command,
)
from ops_bot.new_listing.workflow import ApiResponse, print_response
from ops_bot.responses import BotResponse
from ops_bot.new_listing.workflow import resolve_config_path
from ops_bot.service import handle_user_message


def test_new_listing_template_response() -> None:
    assert (
        asyncio.run(handle_user_message("/new-listing"))
        == NEW_LISTING_INPUT_TEMPLATE
    )


def test_help_response() -> None:
    response = asyncio.run(handle_user_message("/help"))

    assert response is not None
    assert "/health, /ping -> API health check" in response
    assert "/new-listing -> create config and run new-listing workflow" in response
    assert "/new-listing-dryrun -> create config and run dry-run preview" in response
    assert "/setup-stackers -> create and save stacker request body" in response


def test_handle_new_listing_command_saves_config_and_trading_volume(
    monkeypatch,
    tmp_path,
) -> None:
    config_dir = tmp_path / "configs"
    logs_dir = tmp_path / "logs"
    gateway_symbols_path = config_dir / "gateway_symbols.yml"
    trading_volume_path = tmp_path / "trading_volume.json"

    monkeypatch.setattr(
        "ops_bot.new_listing.bot_service.app_settings.new_listing_config_dir",
        config_dir,
    )
    monkeypatch.setattr(
        "ops_bot.new_listing.bot_service.app_settings.new_listing_logs_dir",
        logs_dir,
    )
    monkeypatch.setattr(
        "ops_bot.new_listing.bot_service.app_settings.new_listing_gateway_symbols_path",
        gateway_symbols_path,
    )
    monkeypatch.setattr(
        "ops_bot.new_listing.bot_service.app_settings.new_listing_trading_volume_path",
        trading_volume_path,
    )
    monkeypatch.setattr(
        "ops_bot.new_listing.bot_service.app_settings.new_listing_account_id",
        "ktfsmc15",
    )

    response = handle_new_listing_command(
        {
            "symbol": "ATWO",
            "tier": "C",
            "create_new_gate_way": False,
            "price_decimals": 5,
            "quantity_decimals": 1,
            "feed_port": 41739,
            "gateway_port": 45704,
        },
        dry_run=True,
    )

    assert isinstance(response, BotResponse)
    summary_text, preview = response.message.split("\n\nWorkflow output:\n", maxsplit=1)
    payload = json.loads(summary_text)
    config_path = config_dir / "ATWO.json"

    assert payload["config_path"] == str(config_path)
    assert payload["trading_volume_path"] == str(trading_volume_path)
    assert "Step 1 - Arbitrage Strategy Config" in preview
    assert response.attachments[0] == config_path
    assert config_path.exists()
    assert trading_volume_path.exists()
    assert len(response.attachments) == 2
    assert response.attachments[1].exists()
    assert '"price_tick": 0.00001' in config_path.read_text(encoding="utf-8")

    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["create_new_gate_way"] is False
    assert config["steps"]["1"]["body"]["exchanges"] == "kucoin,gate"
    assert config["steps"]["2"]["body"]["market"] == "spot"
    assert config["steps"]["2"]["body"]["tier"] == "c"
    assert config["steps"]["2"]["body"]["price_tick"] == 0.00001
    assert config["steps"]["4"]["body"]["feed_host"] == "0.0.0.0:41739"
    assert config["steps"]["6"]["body"]["gateway_host"] == "localhost:45704"
    assert config["steps"]["6"]["body"]["feed_host"] == "localhost:41740"

    trading_volume = json.loads(trading_volume_path.read_text(encoding="utf-8"))
    assert "ATWO" in trading_volume["monitoring_symbols"]
    assert trading_volume["requirement_volume"]["kucoin"]["ATWO"] == 1_000_000


def test_handle_new_listing_command_includes_dry_run_preview(
    monkeypatch,
    tmp_path,
) -> None:
    config_dir = tmp_path / "configs"
    logs_dir = tmp_path / "logs"
    gateway_symbols_path = config_dir / "gateway_symbols.yml"
    trading_volume_path = tmp_path / "trading_volume.json"

    monkeypatch.setattr(
        "ops_bot.new_listing.bot_service.app_settings.new_listing_config_dir",
        config_dir,
    )
    monkeypatch.setattr(
        "ops_bot.new_listing.bot_service.app_settings.new_listing_logs_dir",
        logs_dir,
    )
    monkeypatch.setattr(
        "ops_bot.new_listing.bot_service.app_settings.new_listing_gateway_symbols_path",
        gateway_symbols_path,
    )
    monkeypatch.setattr(
        "ops_bot.new_listing.bot_service.app_settings.new_listing_trading_volume_path",
        trading_volume_path,
    )

    response = handle_new_listing_command(
        {
            "symbol": "ATWO",
            "tier": "C",
            "create_new_gate_way": False,
            "price_decimals": 5,
            "quantity_decimals": 1,
            "feed_port": 41739,
            "gateway_port": 45704,
        },
        dry_run=True,
    )

    assert isinstance(response, BotResponse)
    summary_text, preview = response.message.split("\n\nWorkflow output:\n", maxsplit=1)
    payload = json.loads(summary_text)
    assert payload["run_command"] == "uv run new_listing ATWO --dry-run"
    assert payload["mode"] == "dry-run"
    assert "Step 1 - Arbitrage Strategy Config" in preview


def test_update_trading_volume_keeps_all_exchange_requirements_consistent(
    monkeypatch,
    tmp_path,
) -> None:
    trading_volume_path = tmp_path / "trading_volume.json"
    trading_volume_path.write_text(
        json.dumps(
            {
                "monitoring_symbols": ["KAIO"],
                "trading_volume_data_columns": [
                    "timestamp_utc",
                    "product",
                    "base",
                    "usd_volume_24h",
                ],
                "requirement_volume": {
                    "kucoin": {"KAIO": 5000000},
                    "gate": {"KAIO": 5000000},
                },
            },
            indent=4,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "ops_bot.new_listing.bot_service.app_settings.new_listing_trading_volume_path",
        trading_volume_path,
    )

    response = handle_new_listing_command(
        {
            "symbol": "ATWO",
            "tier": "C",
            "create_new_gate_way": False,
            "price_decimals": 5,
            "quantity_decimals": 1,
            "feed_port": 41739,
            "gateway_port": 45704,
        },
        dry_run=True,
    )

    assert isinstance(response, BotResponse)
    trading_volume = json.loads(trading_volume_path.read_text(encoding="utf-8"))
    assert trading_volume["monitoring_symbols"] == ["ATWO", "KAIO"]
    assert trading_volume["requirement_volume"]["kucoin"]["ATWO"] == 1_000_000
    assert trading_volume["requirement_volume"]["gate"]["ATWO"] == 1_000_000


def test_handle_new_listing_command_real_mode_runs_workflow(monkeypatch) -> None:
    calls: list[bool] = []

    monkeypatch.setattr(
        "ops_bot.new_listing.bot_service.save_new_listing_config",
        lambda _config: Path("src/config/new_listing/ATWO.json"),
    )
    monkeypatch.setattr(
        "ops_bot.new_listing.bot_service.update_trading_volume_file",
        lambda _request: Path("/tmp/trading_volume.json"),
    )
    monkeypatch.setattr(
        "ops_bot.new_listing.bot_service._run_listing",
        lambda _config, *, dry_run: (
            calls.append(dry_run) or "real output",
            Path("logs/new_listing/ATWO_test.log"),
        ),
    )

    response = handle_new_listing_command(
        {
            "symbol": "ATWO",
            "tier": "C",
            "create_new_gate_way": False,
            "price_decimals": 5,
            "quantity_decimals": 1,
            "feed_port": 41739,
            "gateway_port": 45704,
        },
        dry_run=False,
    )

    assert isinstance(response, BotResponse)
    summary_text, preview = response.message.split("\n\nWorkflow output:\n", maxsplit=1)
    payload = json.loads(summary_text)
    assert calls == [False]
    assert payload["mode"] == "real"
    assert payload["run_command"] == "uv run new_listing ATWO"
    assert preview.startswith("real output")
    assert "Attached: ATWO.json, ATWO_test.log" in preview


def test_new_listing_request_uses_extracted_exchanges() -> None:
    request = NewListingRequest.from_extracted(
        {
            "symbol": "ATWO",
            "market": "spot",
            "exchanges": "Binance, Kucoin, Gate",
            "tier": "C",
            "create_new_gate_way": False,
            "price_decimals": 5,
            "quantity_decimals": 1,
            "feed_port": 41739,
            "gateway_port": 45704,
        }
    )

    config = build_new_listing_config(request)

    assert request.exchanges == "binance,kucoin,gate"
    assert config["steps"]["1"]["body"]["exchanges"] == "binance,kucoin,gate"
    assert config["steps"]["1"]["body"]["base_ccy"] == "ATWO,ATWO,ATWO"
    assert config["steps"]["1"]["body"]["quote"] == "USDT,USDT,USDT"


def test_resolve_config_path_uses_settings_dir(
    monkeypatch,
    tmp_path,
) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "ATWO.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "ops_bot.new_listing.workflow.app_settings.new_listing_config_dir",
        config_dir,
    )

    class Args:
        config = None
        symbol = "ATWO"

    assert resolve_config_path(Args()) == config_dir / "ATWO.json"


def test_new_listing_print_response_strips_ssh_banner() -> None:
    buffer = StringIO()

    with redirect_stdout(buffer):
        print_response(
            ApiResponse(
                step="1",
                status=200,
                body='Welcome to Ubuntu 22.04.3 LTS\n{"status":"ok"}',
            )
        )

    assert buffer.getvalue() == '\nStep 1 HTTP 200\n{"status":"ok"}\n'
