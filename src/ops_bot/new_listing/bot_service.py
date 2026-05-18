from __future__ import annotations

import io
import json
import re
from contextlib import redirect_stdout
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from ops_bot.responses import BotResponse
from ops_bot.settings import app_settings
from ops_bot.new_listing.workflow import run_new_listing

TIER_VOLUME_REQUIREMENTS = {
    "s": 10_000_000,
    "a": 5_000_000,
    "b": 2_000_000,
    "c": 1_000_000,
}

NEW_LISTING_INPUT_TEMPLATE = """/new-listing
symbol: ATWO
market: spot
tier: C
create_new_gate_way: false
price decimals: 5
quantity decimals: 1
feed port: 41739
gateway port: 45704"""


@dataclass(frozen=True)
class NewListingRequest:
    symbol: str
    market: str
    tier: str
    create_new_gate_way: bool
    price_decimals: int
    quantity_decimals: int
    feed_port: int
    gateway_port: int

    @classmethod
    def from_extracted(cls, extracted: dict[str, Any]) -> "NewListingRequest":
        symbol = _require_text(extracted, "symbol").upper()
        market = _optional_text(extracted.get("market")) or "spot"
        tier = _require_text(extracted, "tier").upper()
        create_new_gate_way = _optional_bool(
            extracted.get("create_new_gate_way"),
            default=False,
        )
        price_decimals = _require_positive_int(extracted, "price_decimals")
        quantity_decimals = _require_positive_int(extracted, "quantity_decimals")
        feed_port = _require_port(extracted, "feed_port")
        gateway_port = _require_port(extracted, "gateway_port")

        if market != "spot":
            raise ValueError("New listing bot setup currently supports spot only.")
        if tier.lower() not in TIER_VOLUME_REQUIREMENTS:
            raise ValueError("Tier must be one of S, A, B, or C.")

        return cls(
            symbol=symbol,
            market=market,
            tier=tier,
            create_new_gate_way=create_new_gate_way,
            price_decimals=price_decimals,
            quantity_decimals=quantity_decimals,
            feed_port=feed_port,
            gateway_port=gateway_port,
        )

def handle_new_listing_command(extracted: dict[str, Any], *, dry_run: bool) -> BotResponse:
    request = NewListingRequest.from_extracted(extracted)
    config = build_new_listing_config(request)
    config_path = save_new_listing_config(config)
    trading_volume_path = update_trading_volume_file(request)
    run_output, log_path = _run_listing(config, dry_run=dry_run)

    summary = {
        "symbol": request.symbol,
        "market": request.market,
        "tier": request.tier,
        "create_new_gate_way": request.create_new_gate_way,
        "price_tick": config["steps"]["2"]["body"]["price_tick"],
        "qty_unit": config["steps"]["2"]["body"]["qty_unit"],
        "gateway_port": request.gateway_port,
        "feed_port": request.feed_port,
        "stacker_feed_port": config["steps"]["6"]["body"]["feed_host"].split(":")[-1],
        "config_path": str(config_path),
        "trading_volume_path": str(trading_volume_path),
        "run_command": (
            f"uv run new_listing {request.symbol} --dry-run"
            if dry_run
            else f"uv run new_listing {request.symbol}"
        ),
        "mode": "dry-run" if dry_run else "real",
    }
    message = "\n".join(
        [
            json.dumps(summary, separators=(",", ":"), ensure_ascii=False),
            "",
            "Workflow output:",
            run_output.rstrip(),
            "",
            f"Attached: {config_path.name}, {log_path.name}",
        ]
    )
    return BotResponse(message=message, attachments=(config_path, log_path))


def build_new_listing_config(request: NewListingRequest) -> dict[str, Any]:
    price_tick = _decimal_tick(request.price_decimals)
    qty_unit = _decimal_tick(request.quantity_decimals)
    compact_symbol = f"{request.symbol}USDT"
    step6_feed_port = request.feed_port + 1

    return {
        "base_endpoint": "http://18.176.93.228",
        "timeout_seconds": 60,
        "create_new_gate_way": request.create_new_gate_way,
        "logs_dir": str(app_settings.new_listing_logs_dir),
        "gateway_symbols_path": str(app_settings.new_listing_gateway_symbols_path),
        "update_gateway_symbols": True,
        "steps": {
            "1": {
                "label": "Arbitrage Strategy Config",
                "endpoint": "/setup_arbitrage_strategy",
                "body": {
                    "exchanges": "kucoin,gate",
                    "base_ccy": f"{request.symbol},{request.symbol}",
                    "quote": "USDT,USDT",
                    "market": request.market,
                    "taker_arb_min_bps": 20,
                    "maker_arb_min_bps": 20000,
                    "max_order_amount": 50,
                    "min_order_amount": 20,
                },
            },
            "2": {
                "label": "Volume Config",
                "endpoint": "/setup_volume_config",
                "body": {
                    "market": request.market,
                    "tier": request.tier.lower(),
                    "base_ccy": request.symbol,
                    "quote_ccy": "USDT",
                    "price_tick": price_tick,
                    "price_tick_size": request.price_decimals,
                    "qty_unit": qty_unit,
                },
            },
            "3": {
                "label": "New Listing Config",
                "endpoint": "/setup_new_listing_config",
                "body": {
                    "exchange": "kucoin",
                    "market": request.market,
                    "symbol": f"{request.symbol}-USDT",
                    "strategy": "slow_mm",
                    "tier": request.tier,
                    "mode": "stacker",
                    "hedge": "false",
                    "auto_start": "true",
                    "auto_restart": "true",
                    "auto_config": "true",
                    "model": "crossover_vol",
                    "vol_param": "1.0",
                    "trading_intensity_param": "1.0",
                    "auto_start_ms": "1800000",
                    "auto_restart_ms": "1209600000",
                    "auto_config_ms": "1209600000",
                },
            },
            "3b": {
                "label": "Set Symbol Config",
                "endpoint": "/set_symbol_config",
                "body": {
                    "base_currency": request.symbol,
                    "quote_currency": "USDT",
                    "market": request.market,
                    "price_tick": price_tick,
                    "size_tick": qty_unit,
                    "min_size": 10,
                    "multiplier": 1,
                    "contract_size": 1,
                    "first_date": 1735822800000,
                },
            },
            "4": {
                "label": "Create Gateway Config File",
                "endpoint": "/setup_new_listing_gateway",
                "body": {
                    "gateway_name": f"emm_mirror_spot_gateway_custom_{compact_symbol}",
                    "market": request.market,
                    "host": f"0.0.0.0:{request.gateway_port}",
                    "feed_host": f"0.0.0.0:{request.feed_port}",
                    "account_id": app_settings.new_listing_account_id,
                },
            },
            "5": {
                "label": "Register Gateway in Supervisorctl",
                "endpoint": "/setup_new_listing_gateway_supervisorctl",
                "body": {
                    "program_name": f"mirror_spot_gateway_custom_{compact_symbol}",
                    "config_path": (
                        "configcpp/exchangemm_PROD/mirror/spot/gateway/"
                        f"emm_mirror_spot_gateway_custom_{compact_symbol}.txtpb"
                    ),
                },
            },
            "6": {
                "label": "Create Feed + Strategy Config Files",
                "endpoint": "/setup_listing_strategy_gateway_feed",
                "body": {
                    "base_ccy": request.symbol,
                    "quote_ccy": "USDT",
                    "market": request.market,
                    "gateway_host": f"localhost:{request.gateway_port}",
                    "feed_host": f"localhost:{step6_feed_port}",
                },
            },
            "7": {
                "label": "Register Feed in Supervisorctl",
                "endpoint": "/setup_new_listing_feed_supervisorctl",
                "body": {
                    "program_name": f"feed_spot_custom_kucoin_{compact_symbol}",
                    "config_path": (
                        "configcpp/exchangemm_PROD/feeds/spot/"
                        f"emm_spot_feed_custom_kucoin_{compact_symbol}.txtpb"
                    ),
                },
            },
            "8": {
                "label": "Register Strategy in Supervisorctl",
                "endpoint": "/setup_new_listing_strategy_supervisorctl",
                "body": {
                    "program_name": f"mirror_spot_listings_strat2_{compact_symbol}",
                    "config_path": (
                        "configcpp/exchangemm_PROD/mirror/spot/strat2/"
                        f"emm_mirror_spot_strat2_{compact_symbol}.txtpb"
                    ),
                },
            },
        },
    }


def save_new_listing_config(config: dict[str, Any]) -> Path:
    config_dir = app_settings.new_listing_config_dir
    config_dir.mkdir(parents=True, exist_ok=True)
    symbol = str(config["steps"]["2"]["body"]["base_ccy"]).upper()
    path = config_dir / f"{symbol}.json"
    path.write_text(_format_config_json(config), encoding="utf-8")
    return path


def update_trading_volume_file(request: NewListingRequest) -> Path:
    path = _resolve_trading_volume_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = {
            "monitoring_symbols": [],
            "trading_volume_data_columns": [
                "timestamp_utc",
                "product",
                "base",
                "usd_volume_24h",
            ],
            "requirement_volume": {"kucoin": {}},
        }

    symbol = request.symbol.upper()
    required_volume = TIER_VOLUME_REQUIREMENTS[request.tier.lower()]

    monitoring_symbols = _normalized_monitoring_symbols(payload.setdefault("monitoring_symbols", []))
    monitoring_symbols.add(symbol)
    payload["monitoring_symbols"] = sorted(monitoring_symbols)

    requirement_volume = payload.setdefault("requirement_volume", {})
    if not isinstance(requirement_volume, dict):
        raise ValueError("trading_volume.json requirement_volume must be a JSON object.")

    if "kucoin" not in requirement_volume or not isinstance(
        requirement_volume.get("kucoin"), dict
    ):
        requirement_volume["kucoin"] = {}

    for exchange, requirements in requirement_volume.items():
        if not isinstance(requirements, dict):
            raise ValueError(
                f"trading_volume.json requirement_volume.{exchange} must be a JSON object."
            )
        requirements[symbol] = required_volume
        requirement_volume[exchange] = dict(sorted(requirements.items()))

    path.write_text(json.dumps(payload, indent=4) + "\n", encoding="utf-8")
    return path


def _decimal_tick(decimals: int) -> float:
    return float(Decimal("1").scaleb(-decimals))


def _resolve_trading_volume_path() -> Path:
    return app_settings.new_listing_trading_volume_path


def _normalized_monitoring_symbols(values: Any) -> set[str]:
    if not isinstance(values, list):
        raise ValueError("trading_volume.json monitoring_symbols must be a JSON array.")
    return {
        str(value).strip().upper()
        for value in values
        if str(value).strip()
    }


def _format_config_json(config: dict[str, Any]) -> str:
    rendered = json.dumps(config, indent=4) + "\n"
    return re.sub(
        r"(?<=:\s)(-?\d+(?:\.\d+)?e-\d+)",
        lambda match: format(float(match.group(1)), ".10f").rstrip("0").rstrip("."),
        rendered,
    )


def _run_listing(config: dict[str, Any], *, dry_run: bool) -> tuple[str, Path]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        log_path = run_new_listing(config, dry_run=dry_run)
    return buffer.getvalue(), log_path


def _require_text(extracted: dict[str, Any], key: str) -> str:
    value = extracted.get(key)
    if value is None:
        raise ValueError(f"Missing required field: {key}")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"Missing required field: {key}")
    return normalized


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized.lower() or None


def _require_positive_int(extracted: dict[str, Any], key: str) -> int:
    raw_value = extracted.get(key)
    if raw_value is None:
        raise ValueError(f"Missing required field: {key}")
    value = int(raw_value)
    if value < 0:
        raise ValueError(f"{key} must be zero or greater.")
    return value


def _require_port(extracted: dict[str, Any], key: str) -> int:
    value = _require_positive_int(extracted, key)
    if value <= 0 or value > 65535:
        raise ValueError(f"{key} must be a valid port.")
    return value


def _optional_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ValueError("create_new_gate_way must be true or false.")
