from __future__ import annotations

import pytest

from ops_bot.ops_requests import build_ops_call
from ops_bot.routing import route_message


def test_route_transfer_slash_command() -> None:
    routed = route_message("/transfer sub to main 10 usdt from kc")

    assert routed is not None
    assert routed.agent == "transfer"
    assert routed.question == "sub to main 10 usdt from kc"


def test_route_balance_keyword() -> None:
    routed = route_message("how much usdt do I have on kucoin?")

    assert routed is not None
    assert routed.agent == "balance"


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

