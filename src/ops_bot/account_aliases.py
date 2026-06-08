from __future__ import annotations

import json

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
ACCOUNT_ALIASES_BY_EXCHANGE = {
    "bin": ("fr",),
    "binance": ("fr",),
    "binf": ("fr",),
    "binancef": ("fr",),
    "byb": ("fr",),
    "bybit": ("fr",),
    "fintrade": (
        "fintrade1",
        "fintrade2",
        "fintrade3",
        "fintrade4",
        "fintrade5",
    ),
    "fintradef": (
        "fintrade1",
        "fintrade2",
        "fintrade3",
        "fintrade4",
        "fintrade5",
    ),
    "gate": ("fr",),
    "gateio": ("fr",),
    "kc": (
        "spotarb",
        "fdvstrat",
        "-vefrspot",
        "volumenewlisting",
        "liquidity",
        "spotinv",
        "mirroracc2",
        "colostrat1",
        "rfqhedge",
        "FR2",
    ),
    "kucoin": (
        "spotarb",
        "fdvstrat",
        "-vefrspot",
        "volumenewlisting",
        "liquidity",
        "spotinv",
        "mirroracc2",
        "colostrat1",
        "rfqhedge",
        "FR2",
    ),
    "kcf": (
        "colostrat1",
        "perp_API_1_volume",
        "perp_API_2_volume",
        "perp_API_3_volume",
        "perp_API_4_volume",
        "perp_API_5_volume",
        "perp_API_6_volume",
    ),
    "kucoinf": (
        "colostrat1",
        "perp_API_1_volume",
        "perp_API_2_volume",
        "perp_API_3_volume",
        "perp_API_4_volume",
        "perp_API_5_volume",
        "perp_API_6_volume",
    ),
}
ACCOUNT_ALIAS_DISPLAY_EXCHANGES = {
    "bin": "binance",
    "binance": "binance",
    "binf": "binance futures",
    "binancef": "binance futures",
    "byb": "bybit",
    "bybit": "bybit",
    "gate": "gate",
    "gateio": "gate",
    "kc": "kucoin",
    "kucoin": "kucoin",
    "kcf": "kucoin futures",
    "kucoinf": "kucoin futures",
}


def format_account_aliases_for_exchange(exchange: str | None) -> str | None:
    normalized = _normalize_exchange(exchange)
    if not normalized:
        return None
    aliases = ACCOUNT_ALIASES_BY_EXCHANGE.get(normalized)
    if aliases is None:
        return None
    display_exchange = ACCOUNT_ALIAS_DISPLAY_EXCHANGES.get(normalized, normalized)
    return f"{display_exchange} account: {json.dumps(list(aliases))}"


def format_all_account_aliases() -> str:
    accounts_by_display_exchange: dict[str, tuple[str, ...]] = {}
    for exchange, aliases in ACCOUNT_ALIASES_BY_EXCHANGE.items():
        display_exchange = ACCOUNT_ALIAS_DISPLAY_EXCHANGES.get(exchange, exchange)
        accounts_by_display_exchange[display_exchange] = aliases
    return "\n".join(
        f"{exchange} account: {json.dumps(list(accounts))}"
        for exchange, accounts in sorted(accounts_by_display_exchange.items())
    )


def _normalize_exchange(exchange: str | None) -> str | None:
    if exchange is None:
        return None
    normalized = str(exchange).strip().lower()
    return normalized or None
