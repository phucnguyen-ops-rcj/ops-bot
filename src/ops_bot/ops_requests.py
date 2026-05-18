from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from ops_bot.clients.ops_api import normalize_symbol
from ops_bot.routing import AgentName

SUPPORTED_EXCHANGES = {
    "kc",
    "kcf",
    "kucoin",
    "kucoinf",
    "bybit",
    "byb",
    "okx",
    "gate",
    "gateio",
    "binance",
    "bin",
    "binf",
    "binancef",
    "bitget",
    "mexc",
    "fintrade",
    "fintradef",
}
FUTURES_EXCHANGES = {"kcf", "binf", "fintradef"}
TRANSFER_MODES = {
    "sub_to_main",
    "main_to_sub",
    "withdraw",
    "future_to_spot",
    "spot_to_future",
    "future_to_main",
    "main_to_future",
    "trading_to_funding",
}


@dataclass(frozen=True)
class OpsCall:
    endpoint: str
    method: Literal["GET", "POST"]
    authenticated: bool
    payload: dict[str, Any]


def build_ops_call(agent: AgentName, extracted: dict[str, Any]) -> OpsCall:
    if agent == "health":
        return OpsCall("/health", "GET", False, {})
    if agent == "balance":
        return _build_balance_call(extracted)
    if agent == "transfer":
        return _build_transfer_call(extracted)
    if agent == "monitor":
        update_time = extracted.get("update_time") or 10
        return OpsCall("/run-monitor", "POST", True, {"update_time": int(update_time)})
    if agent == "volume_fills":
        return _build_volume_fills_call(extracted)
    if agent == "stacker_status":
        return _build_stacker_status_call(extracted)
    raise ValueError(f"Unsupported agent: {agent}")


def _build_balance_call(extracted: dict[str, Any]) -> OpsCall:
    exchange = _normalize_optional_string(extracted.get("exchange"))
    if not exchange:
        raise ValueError("Which exchange?")
    if exchange not in SUPPORTED_EXCHANGES:
        raise ValueError(f"Unsupported exchange for balance: {exchange}")

    payload = {
        "exchange": exchange,
        "account": _normalize_optional_string(extracted.get("account")) or "main",
        "token": (_normalize_optional_string(extracted.get("token")) or "USDT").upper(),
    }
    market = _normalize_optional_string(extracted.get("market"))
    if exchange in FUTURES_EXCHANGES and not market:
        raise ValueError("Which futures market?")
    if market:
        payload["market"] = market

    return OpsCall("/get-balance", "POST", True, payload)


def _build_transfer_call(extracted: dict[str, Any]) -> OpsCall:
    mode = _normalize_optional_string(extracted.get("mode"))
    token = _normalize_optional_string(extracted.get("token"))
    from_exchange = _normalize_optional_string(extracted.get("from_exchange"))
    amount = extracted.get("amount")

    missing = []
    if not mode:
        missing.append("mode")
    if not token:
        missing.append("token")
    if not from_exchange:
        missing.append("from_exchange")
    if amount is None:
        missing.append("amount")
    if missing:
        raise ValueError(f"Missing required transfer field(s): {', '.join(missing)}")

    assert mode is not None
    assert token is not None
    assert from_exchange is not None
    if mode not in TRANSFER_MODES:
        raise ValueError(f"Unsupported transfer mode: {mode}")
    if from_exchange not in SUPPORTED_EXCHANGES:
        raise ValueError(f"Unsupported from_exchange for transfer: {from_exchange}")

    amount_float = float(amount)
    if amount_float <= 0:
        raise ValueError("Transfer amount must be positive.")

    payload: dict[str, Any] = {
        "mode": mode,
        "token": token.upper(),
        "from_exchange": from_exchange,
        "amount": amount_float,
    }

    sub_account_name = _normalize_optional_string(extracted.get("sub_account_name"))
    to_exchange = _normalize_optional_string(extracted.get("to_exchange"))

    if _requires_sub_account(mode, from_exchange) and not sub_account_name:
        raise ValueError("Which sub-account name?")
    if sub_account_name:
        payload["sub_account_name"] = sub_account_name

    if mode == "withdraw" and not to_exchange:
        raise ValueError("Withdraw to which exchange?")
    if to_exchange:
        if to_exchange not in SUPPORTED_EXCHANGES:
            raise ValueError(f"Unsupported to_exchange for withdraw: {to_exchange}")
        payload["to_exchange"] = to_exchange

    if mode == "trading_to_funding" and from_exchange != "okx":
        raise ValueError("trading_to_funding is OKX only.")
    if mode in {"future_to_main", "main_to_future"} and from_exchange != "kcf":
        raise ValueError(f"{mode} is kcf only.")

    return OpsCall("/run-transfer", "POST", True, payload)


def _build_volume_fills_call(extracted: dict[str, Any]) -> OpsCall:
    symbol = _normalize_symbol_field(extracted.get("symbol"))
    if not symbol:
        raise ValueError("Which symbol?")

    normalized_symbol = normalize_symbol(symbol)
    base_currency, quote_currency = normalized_symbol.split("-", maxsplit=1)
    payload: dict[str, Any] = {
        "base_currency": base_currency,
        "quote_currency": quote_currency,
    }

    date = _normalize_optional_string(extracted.get("date"))
    if date:
        payload["date"] = _validate_compact_date(date)

    return OpsCall("/get_volume_strategy_fills", "POST", True, payload)


def _build_stacker_status_call(extracted: dict[str, Any]) -> OpsCall:
    symbol = _normalize_symbol_field(extracted.get("symbol"))
    if not symbol:
        raise ValueError("Which symbol?")

    payload: dict[str, Any] = {"symbol": normalize_symbol(symbol)}

    date = _normalize_optional_string(extracted.get("date"))
    if date:
        payload["date"] = _validate_compact_date(date)

    return OpsCall("/get_stacker_accepted_orders", "POST", True, payload)


def _requires_sub_account(mode: str, from_exchange: str) -> bool:
    if mode in {"future_to_spot", "spot_to_future", "future_to_main", "main_to_future"}:
        return from_exchange == "kcf"
    return mode in {"sub_to_main", "main_to_sub"} and from_exchange == "kc"


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized.lower() or None


def _normalize_symbol_field(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper().replace("_", "-").replace("/", "-")
    return normalized or None


def _validate_compact_date(value: str) -> str:
    if len(value) != 8 or not value.isdigit():
        raise ValueError("Date must be in YYYYMMDD format.")
    return value
