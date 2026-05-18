from __future__ import annotations

import pytest

from ops_bot.ops_requests import build_ops_call
from ops_bot.routing import route_message
from ops_bot.service import _format_response


def test_route_transfer_slash_command() -> None:
    routed = route_message("/transfer sub to main 10 usdt from kc")

    assert routed is not None
    assert routed.agent == "transfer"
    assert routed.question == "sub to main 10 usdt from kc"


def test_route_balance_keyword() -> None:
    routed = route_message("how much usdt do I have on kucoin?")

    assert routed is not None
    assert routed.agent == "balance"


def test_route_volume_fills_slash_command() -> None:
    routed = route_message("/volume-fills KAIO")

    assert routed is not None
    assert routed.agent == "volume_fills"
    assert routed.question == "KAIO"


def test_route_stacker_status_keyword() -> None:
    routed = route_message("check status for KAIO-USDT")

    assert routed is not None
    assert routed.agent == "stacker_status"


def test_route_new_listing_slash_command() -> None:
    routed = route_message("/new-listing symbol: ATWO")

    assert routed is not None
    assert routed.agent == "new_listing"


def test_route_help_slash_command() -> None:
    routed = route_message("/help")

    assert routed is not None
    assert routed.agent == "help"


def test_route_setup_stackers_slash_command() -> None:
    routed = route_message('/setup-stackers {"base_ccy":"SHARE"}')

    assert routed is not None
    assert routed.agent == "setup_stackers"


def test_removed_newlisting_alias_no_longer_routes() -> None:
    assert route_message("/newlisting") is None


def test_build_balance_call_defaults_token_and_account() -> None:
    call = build_ops_call("balance", {"exchange": "kucoin", "missing_fields": []})

    assert call.endpoint == "/get-balance"
    assert call.method == "POST"
    assert call.payload == {
        "exchange": "kucoin",
        "account": "main",
        "token": "USDT",
    }


def test_build_balance_call_requires_futures_market() -> None:
    with pytest.raises(ValueError, match="Which futures market"):
        build_ops_call("balance", {"exchange": "kcf", "missing_fields": []})


def test_build_transfer_call() -> None:
    call = build_ops_call(
        "transfer",
        {
            "mode": "sub_to_main",
            "token": "usdt",
            "from_exchange": "kc",
            "amount": 10,
            "sub_account_name": "ktfsmc15",
            "missing_fields": [],
        },
    )

    assert call.endpoint == "/run-transfer"
    assert call.payload == {
        "mode": "sub_to_main",
        "token": "USDT",
        "from_exchange": "kc",
        "amount": 10.0,
        "sub_account_name": "ktfsmc15",
    }


def test_build_transfer_call_requires_withdraw_destination() -> None:
    with pytest.raises(ValueError, match="Withdraw to which exchange"):
        build_ops_call(
            "transfer",
            {
                "mode": "withdraw",
                "token": "USDT",
                "from_exchange": "kc",
                "amount": 10,
                "missing_fields": [],
            },
        )


def test_build_volume_fills_call_defaults_quote_currency() -> None:
    call = build_ops_call("volume_fills", {"symbol": "kaio", "missing_fields": []})

    assert call.endpoint == "/get_volume_strategy_fills"
    assert call.method == "POST"
    assert call.payload == {
        "base_currency": "KAIO",
        "quote_currency": "USDT",
    }


def test_build_volume_fills_call_accepts_date() -> None:
    call = build_ops_call(
        "volume_fills",
        {"symbol": "KAIO-USDT", "date": "20260504", "missing_fields": []},
    )

    assert call.payload == {
        "base_currency": "KAIO",
        "quote_currency": "USDT",
        "date": "20260504",
    }


def test_build_stacker_status_call_normalizes_symbol() -> None:
    call = build_ops_call(
        "stacker_status",
        {"symbol": "kaio_usdt", "date": "20260504", "missing_fields": []},
    )

    assert call.endpoint == "/get_stacker_accepted_orders"
    assert call.payload == {
        "symbol": "KAIO-USDT",
        "date": "20260504",
    }


def test_build_stacker_status_call_rejects_bad_date() -> None:
    with pytest.raises(ValueError, match="YYYYMMDD"):
        build_ops_call(
            "stacker_status",
            {"symbol": "KAIO-USDT", "date": "2026-05-04", "missing_fields": []},
        )


def test_format_balance_response_returns_compact_json_only() -> None:
    call = build_ops_call("balance", {"exchange": "kc", "missing_fields": []})
    body = """
Welcome to Ubuntu 22.04.3 LTS

*** System restart required ***
{"account":"main","balance":7.72886,"code":200,"exchange":"kc","message":"success","request_id":"ef09efbc071f40deb4bf524669cc9603","token":"USDT"}
"""

    assert _format_response(call, 200, body) == (
        '{"account":"main","balance":7.72886,"exchange":"kc","token":"USDT"}'
    )


def test_format_non_json_response_omits_method_and_status() -> None:
    call = build_ops_call("health", {})

    assert _format_response(call, 500, "service unavailable\n") == (
        "service unavailable"
    )
