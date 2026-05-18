from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from ops_bot.clients.ops_api import OpsApiClient
from ops_bot.response_format import format_ops_response_body
from ops_bot.responses import BotResponse
from ops_bot.settings import app_settings

SETUP_STACKERS_INPUT_TEMPLATE = """{
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
    "count": 50
  },
  "sell": {
    "min_price": 0.5,
    "max_price": 1.75,
    "min_quantity": 75,
    "max_quantity": 500,
    "count": 50
  }
}"""


@dataclass(frozen=True)
class SideRange:
    min_price: Decimal
    max_price: Decimal
    min_quantity: Decimal
    max_quantity: Decimal
    count: int

    @classmethod
    def from_dict(cls, payload: dict[str, Any], *keys: str) -> "SideRange":
        section, key = _require_one_of_objects(payload, *keys)
        count = int(section.get("count", 3))
        if count <= 0:
            raise ValueError(f"{key}.count must be positive.")
        min_price = _require_decimal(section, "min_price", label=f"{key}.min_price")
        max_price = _require_decimal(section, "max_price", label=f"{key}.max_price")
        min_quantity = _require_decimal(
            section, "min_quantity", label=f"{key}.min_quantity"
        )
        max_quantity = _require_decimal(
            section, "max_quantity", label=f"{key}.max_quantity"
        )
        if min_price > max_price:
            raise ValueError(f"{key}.min_price cannot exceed {key}.max_price.")
        if min_quantity > max_quantity:
            raise ValueError(f"{key}.min_quantity cannot exceed {key}.max_quantity.")
        return cls(min_price, max_price, min_quantity, max_quantity, count)


@dataclass(frozen=True)
class GeneralConfig:
    price_decimals: int
    quantity_step_decimals: int
    min_price: Decimal
    max_price: Decimal
    min_order_quantity: Decimal
    max_quantity: Decimal

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GeneralConfig":
        section = _require_object(payload, "general")
        price_decimals = int(section.get("price_decimals"))
        quantity_step_decimals = int(section.get("quantity_step_decimals"))
        if price_decimals < 0 or quantity_step_decimals < 0:
            raise ValueError("general decimal settings must be zero or greater.")
        min_price = _require_decimal(section, "min_price", label="general.min_price")
        max_price = _require_decimal(section, "max_price", label="general.max_price")
        min_order_quantity = _require_decimal(
            section, "min_order_quantity", label="general.min_order_quantity"
        )
        max_quantity = _require_decimal(
            section, "max_quantity", label="general.max_quantity"
        )
        if min_price > max_price:
            raise ValueError("general.min_price cannot exceed general.max_price.")
        if min_order_quantity > max_quantity:
            raise ValueError(
                "general.min_order_quantity cannot exceed general.max_quantity."
            )
        return cls(
            price_decimals=price_decimals,
            quantity_step_decimals=quantity_step_decimals,
            min_price=min_price,
            max_price=max_price,
            min_order_quantity=min_order_quantity,
            max_quantity=max_quantity,
        )


@dataclass(frozen=True)
class StackerSetupRequest:
    base_ccy: str
    quote_ccy: str
    market: str
    exchanges: str
    feed_host: str
    gateway_host: str
    general: GeneralConfig
    buy: SideRange
    sell: SideRange

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "StackerSetupRequest":
        base_ccy = _require_text(payload, "base_ccy").upper()
        quote_ccy = _require_text(payload, "quote_ccy").upper()
        market = _require_text(payload, "market").lower()
        exchanges = _require_text(payload, "exchanges").lower()
        feed_host = _require_text(payload, "feed_host")
        gateway_host = _require_text(payload, "gateway_host")
        return cls(
            base_ccy=base_ccy,
            quote_ccy=quote_ccy,
            market=market,
            exchanges=exchanges,
            feed_host=feed_host,
            gateway_host=gateway_host,
            general=GeneralConfig.from_dict(payload),
            buy=SideRange.from_dict(payload, "buy", "bid"),
            sell=SideRange.from_dict(payload, "sell", "ask"),
        )


def handle_setup_stackers_command(question: str, *, dry_run: bool) -> BotResponse:
    payload = _extract_json_payload(question)
    request = StackerSetupRequest.from_payload(payload)
    body = build_stacker_request_body(request)
    body_path = save_stacker_body(body, request.base_ccy)
    if dry_run:
        save_stacker_log(request.base_ccy, payload, body, dry_run=True)
        return BotResponse(
            message=_format_json_body(body),
            attachments=(body_path,),
        )

    client = OpsApiClient(
        base_endpoint=app_settings.rcj_ops_base_endpoint,
        timeout_seconds=app_settings.rcj_ops_timeout_seconds,
        execution_mode=app_settings.rcj_ops_execution_mode,
        ssh_host=app_settings.rcj_ops_ssh_host,
    )
    response = client.post("/setup_stacker_config", body)
    save_stacker_log(
        request.base_ccy,
        payload,
        body,
        dry_run=False,
        response_status=response.status,
        response_body=response.body,
    )
    return BotResponse(
        message=format_ops_response_body("/setup_stacker_config", response.body),
        attachments=(body_path,),
    )


def build_stacker_request_body(request: StackerSetupRequest) -> dict[str, Any]:
    tick_size = _decimal_step(request.general.price_decimals)
    quantity_step_size = _decimal_step(request.general.quantity_step_decimals)
    buy_stackers = _generate_stackers(
        request.buy,
        price_decimals=request.general.price_decimals,
        quantity_decimals=4,
    )
    sell_stackers = _generate_stackers(
        request.sell,
        price_decimals=request.general.price_decimals,
        quantity_decimals=4,
    )
    return {
        "exchanges": request.exchanges,
        "base_ccy": request.base_ccy,
        "quote_ccy": request.quote_ccy,
        "market": request.market,
        "feed_host": request.feed_host,
        "gateway_host": request.gateway_host,
        "tick_size": float(tick_size),
        "quantity_step_size": float(quantity_step_size),
        "min_price": float(request.general.min_price),
        "max_price": float(request.general.max_price),
        "min_quantity": float(request.general.min_order_quantity),
        "max_quantity": float(request.general.max_quantity),
        "buy_stackers": _stackers_proto_string(buy_stackers, request.general.price_decimals),
        "sell_stackers": _stackers_proto_string(sell_stackers, request.general.price_decimals),
    }


def save_stacker_config(payload: dict[str, Any], symbol: str) -> Path:
    path = app_settings.stacker_config_dir
    path.mkdir(parents=True, exist_ok=True)
    config_path = path / f"{symbol}.json"
    config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return config_path


def save_stacker_body(body: dict[str, Any], symbol: str) -> Path:
    path = app_settings.stacker_config_dir
    path.mkdir(parents=True, exist_ok=True)
    body_path = path / f"{symbol}.request.json"
    body_path.write_text(_format_json_body(body), encoding="utf-8")
    return body_path


def save_stacker_log(
    symbol: str,
    source_payload: dict[str, Any],
    request_body: dict[str, Any],
    *,
    dry_run: bool,
    response_status: int | None = None,
    response_body: str | None = None,
) -> Path:
    log_dir = app_settings.stacker_logs_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    path = log_dir / f"{symbol}_{timestamp}.log"
    lines = [
        f"timestamp_utc: {datetime.now(timezone.utc).isoformat()}",
        f"dry_run: {dry_run}",
        "source:",
        json.dumps(source_payload, indent=2, sort_keys=True),
        "request_body:",
        json.dumps(request_body, indent=2, sort_keys=True),
    ]
    if response_status is not None:
        lines.extend(
            [
                f"response_status: {response_status}",
                "response_body:",
                (response_body or "").rstrip(),
            ]
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _extract_json_payload(question: str) -> dict[str, Any]:
    stripped = question.strip()
    if not stripped:
        raise ValueError("Provide a JSON payload after the command.")
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Provide a valid JSON object after the command.")
    try:
        payload = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON payload: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Stacker setup payload must be a JSON object.")
    return payload


def _generate_stackers(
    side: SideRange,
    *,
    price_decimals: int,
    quantity_decimals: int,
) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    max_attempts = max(side.count * 20, 100)
    attempts = 0
    while len(entries) < side.count:
        attempts += 1
        if attempts > max_attempts:
            raise ValueError(
                "Could not generate enough unique stackers for the requested count. "
                "Widen the price/quantity ranges or reduce count."
            )
        price = _random_decimal(side.min_price, side.max_price, price_decimals)
        quantity = _random_decimal(
            side.min_quantity,
            side.max_quantity,
            quantity_decimals,
        )
        formatted_price = _format_decimal(price, price_decimals)
        formatted_quantity = _format_decimal(quantity, quantity_decimals)
        key = (formatted_price, formatted_quantity)
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            {
                "price": formatted_price,
                "original_quantity": formatted_quantity,
            }
        )
    return sorted(entries, key=lambda entry: Decimal(entry["price"]), reverse=True)


def _stackers_proto_string(
    entries: list[dict[str, str]],
    price_decimals: int,
) -> str:
    objects = [
        "{price: "
        f"{entry['price']} "
        f"original_quantity: {entry['original_quantity']}"
        "}"
        for entry in entries
    ]
    return "[" + ",".join(objects) + "]"


def _format_json_body(body: dict[str, Any]) -> str:
    rendered = json.dumps(body, indent=2, ensure_ascii=False) + "\n"
    return re.sub(
        r"(?<=:\s)(-?\d+(?:\.\d+)?e-\d+)",
        lambda match: format(float(match.group(1)), ".10f").rstrip("0").rstrip("."),
        rendered,
    )


def _decimal_step(decimals: int) -> Decimal:
    return Decimal("1").scaleb(-decimals)


def _random_decimal(minimum: Decimal, maximum: Decimal, decimals: int) -> Decimal:
    random_value = (
        Decimal(str(random.random())) * (maximum - minimum)
    ) + minimum
    quant = _decimal_step(decimals)
    return random_value.quantize(quant, rounding=ROUND_HALF_UP)


def _format_decimal(value: Decimal, decimals: int) -> str:
    return f"{value:.{decimals}f}"


def _require_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if value is None:
        raise ValueError(f"Missing required field: {key}")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"Missing required field: {key}")
    return normalized


def _require_object(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a JSON object.")
    return value


def _require_one_of_objects(payload: dict[str, Any], *keys: str) -> tuple[dict[str, Any], str]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            return value, key
    joined = " or ".join(keys)
    raise ValueError(f"{joined} must be a JSON object.")


def _require_decimal(payload: dict[str, Any], key: str, *, label: str) -> Decimal:
    value = payload.get(key)
    if value is None:
        raise ValueError(f"Missing required field: {label}")
    try:
        return Decimal(str(value))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"{label} must be numeric.") from exc
