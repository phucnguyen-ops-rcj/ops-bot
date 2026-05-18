from __future__ import annotations

import asyncio
import json
from pathlib import Path

from ops_bot.clients.ops_api import OpsApiResponse
from ops_bot.responses import BotResponse
from ops_bot.service import handle_user_message
from ops_bot.stackers.bot_service import SETUP_STACKERS_INPUT_TEMPLATE


def test_setup_stackers_template_response() -> None:
    assert asyncio.run(handle_user_message("/setup-stackers")) == SETUP_STACKERS_INPUT_TEMPLATE


def test_setup_stackers_builds_and_saves_request_body(
    monkeypatch,
    tmp_path,
) -> None:
    config_dir = tmp_path / "stackers" / "config"
    logs_dir = tmp_path / "stackers" / "logs"
    monkeypatch.setattr(
        "ops_bot.stackers.bot_service.app_settings.stacker_config_dir",
        config_dir,
    )
    monkeypatch.setattr(
        "ops_bot.stackers.bot_service.app_settings.stacker_logs_dir",
        logs_dir,
    )

    values = iter([0.10, 0.20, 0.50, 0.30, 0.30, 0.40, 0.40, 0.10, 0.20, 0.20, 0.80, 0.30])
    monkeypatch.setattr(
        "ops_bot.stackers.bot_service.random.random",
        lambda: next(values),
    )

    message = """/setup-stackers-dryrun
{
  "base_ccy": "SHARE",
  "quote_ccy": "USDT",
  "market": "spot",
  "exchanges": "kucoin",
  "feed_host": "0.0.0.0:41740",
  "gateway_host": "0.0.0.0:41799",
  "general": {
    "price_decimals": 5,
    "quantity_step_decimals": 1,
    "min_price": 0.00001,
    "max_price": 1.75,
    "min_order_quantity": 10,
    "max_quantity": 100000000000
  },
  "buy": {
    "min_price": 0.00001,
    "max_price": 0.02,
    "min_quantity": 500,
    "max_quantity": 5000,
    "count": 3
  },
  "sell": {
    "min_price": 0.5,
    "max_price": 1.75,
    "min_quantity": 75,
    "max_quantity": 500,
    "count": 3
  }
}"""

    response = asyncio.run(handle_user_message(message))

    assert isinstance(response, BotResponse)
    body = json.loads(response.message)
    assert body["base_ccy"] == "SHARE"
    assert body["tick_size"] == 0.00001
    assert body["quantity_step_size"] == 0.1
    assert body["buy_stackers"] == (
        "[{price: 0.01001 original_quantity: 1850.0000},"
        "{price: 0.00601 original_quantity: 2300.0000},"
        "{price: 0.00201 original_quantity: 1400.0000}]"
    )
    assert body["sell_stackers"] == (
        "[{price: 1.50000 original_quantity: 202.5000},"
        "{price: 1.00000 original_quantity: 117.5000},"
        "{price: 0.75000 original_quantity: 160.0000}]"
    )

    request_path = config_dir / "SHARE.request.json"
    assert request_path.exists()
    assert response.attachments == (request_path,)
    assert '"tick_size": 0.00001' in request_path.read_text(encoding="utf-8")
    log_files = list(logs_dir.glob("SHARE_*.log"))
    assert len(log_files) == 1
    assert "dry_run: True" in log_files[0].read_text(encoding="utf-8")


def test_setup_stackers_executes_api_in_real_mode(
    monkeypatch,
    tmp_path,
) -> None:
    config_dir = tmp_path / "stackers" / "config"
    logs_dir = tmp_path / "stackers" / "logs"
    monkeypatch.setattr(
        "ops_bot.stackers.bot_service.app_settings.stacker_config_dir",
        config_dir,
    )
    monkeypatch.setattr(
        "ops_bot.stackers.bot_service.app_settings.stacker_logs_dir",
        logs_dir,
    )

    values = iter([0.10, 0.20, 0.50, 0.30])
    monkeypatch.setattr(
        "ops_bot.stackers.bot_service.random.random",
        lambda: next(values),
    )

    captured: dict[str, object] = {}

    def fake_post(self, endpoint: str, payload: dict[str, object]) -> OpsApiResponse:
        captured["endpoint"] = endpoint
        captured["payload"] = payload
        return OpsApiResponse(
            endpoint=endpoint,
            status=200,
            body='{"status":"ok"}',
            payload=payload,
        )

    monkeypatch.setattr("ops_bot.stackers.bot_service.OpsApiClient.post", fake_post)

    message = """/setup-stackers
{
  "base_ccy": "SHARE",
  "quote_ccy": "USDT",
  "market": "spot",
  "exchanges": "kucoin",
  "feed_host": "0.0.0.0:41740",
  "gateway_host": "0.0.0.0:41799",
  "general": {
    "price_decimals": 5,
    "quantity_step_decimals": 1,
    "min_price": 0.00001,
    "max_price": 1.75,
    "min_order_quantity": 10,
    "max_quantity": 100000000000
  },
  "buy": {
    "min_price": 0.00001,
    "max_price": 0.02,
    "min_quantity": 500,
    "max_quantity": 5000,
    "count": 1
  },
  "sell": {
    "min_price": 0.5,
    "max_price": 1.75,
    "min_quantity": 75,
    "max_quantity": 500,
    "count": 1
  }
}"""

    response = asyncio.run(handle_user_message(message))

    assert isinstance(response, BotResponse)
    assert response.message == '{"status":"ok"}'
    assert captured["endpoint"] == "/setup_stacker_config"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["buy_stackers"] == "[{price: 0.00201 original_quantity: 1400.0000}]"
    assert payload["sell_stackers"] == "[{price: 1.12500 original_quantity: 202.5000}]"

    request_path = config_dir / "SHARE.request.json"
    assert response.attachments == (request_path,)
    log_files = list(logs_dir.glob("SHARE_*.log"))
    assert len(log_files) == 1
    log_text = log_files[0].read_text(encoding="utf-8")
    assert "dry_run: False" in log_text
    assert "response_status: 200" in log_text
    assert '{"status":"ok"}' in log_text
