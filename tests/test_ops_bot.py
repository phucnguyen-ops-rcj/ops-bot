from __future__ import annotations

import asyncio

import pytest

from ops_bot.ops_requests import build_ops_call
from ops_bot.routing import route_message
from ops_bot.service import _format_response, handle_user_message


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


def test_route_stackers_status_slash_command() -> None:
    routed = route_message("/stackers-status KAIO-USDT")

    assert routed is not None
    assert routed.agent == "stacker_status"
    assert routed.question == "KAIO-USDT"


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


def test_route_accounts_slash_command() -> None:
    routed = route_message("/accounts")

    assert routed is not None
    assert routed.agent == "accounts"


def test_accounts_command_lists_all_maintained_account_groups() -> None:
    response = asyncio.run(handle_user_message("/accounts"))

    assert isinstance(response, str)
    assert response.startswith('binance account: ["fr"]')
    assert 'fintrade account: ["fintrade1", "fintrade2"' in response
    assert 'kucoin account: ["spotarb", "fdvstrat"' in response
    assert 'kucoin futures account: ["colostrat1", "perp_API_1_volume"' in response
    assert response.count("binance account:") == 1
    assert response.count("kucoin account:") == 1


def test_route_setup_stackers_slash_command() -> None:
    routed = route_message('/setup-stackers {"base_ccy":"SHARE"}')

    assert routed is not None
    assert routed.agent == "setup_stackers"


def test_route_update_stackers_slash_command() -> None:
    routed = route_message('/update-stackers {"base_ccy":"RAVE"}')

    assert routed is not None
    assert routed.agent == "update_stackers"


def test_route_schedule_stacker_slash_command() -> None:
    routed = route_message('/schedule-stackers {"symbol":"BILL"}')

    assert routed is not None
    assert routed.agent == "schedule_prefect"


def test_route_schedule_new_listing_slash_command() -> None:
    routed = route_message('/schedule-new-listing {"symbol":"BILL"}')

    assert routed is not None
    assert routed.agent == "schedule_prefect"


def test_route_remove_schedules_slash_command() -> None:
    routed = route_message('/remove-schedules {"flow_run_id":"abc"}')

    assert routed is not None
    assert routed.agent == "schedule_prefect"


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


def test_format_failed_balance_response_includes_exchange_accounts() -> None:
    call = build_ops_call(
        "balance",
        {"exchange": "bin", "account": "volume2", "missing_fields": []},
    )
    body = (
        '{"code":404,"message":"Sub-account \'volume2\' not found under exchange '
        '\'bin\'","request_id":"939f95926043484a892e8518556ccff6"}'
    )

    assert _format_response(call, 200, body) == (
        body + '\nbinance account: ["fr"]'
    )


def test_format_failed_transfer_response_includes_source_exchange_accounts() -> None:
    call = build_ops_call(
        "transfer",
        {
            "mode": "sub_to_main",
            "token": "usdt",
            "from_exchange": "kc",
            "amount": 10,
            "sub_account_name": "volume2",
            "missing_fields": [],
        },
    )
    body = (
        '{"code":404,"message":"Sub-account \'volume2\' not found under exchange '
        '\'kc\'","request_id":"939f95926043484a892e8518556ccff6"}'
    )

    assert _format_response(call, 200, body) == (
        body
        + '\nkucoin account: ["spotarb", "fdvstrat", "-vefrspot", '
        '"volumenewlisting", "liquidity", "spotinv", "mirroracc2", '
        '"colostrat1", "rfqhedge", "FR2"]'
    )


def test_format_failed_transfer_response_includes_both_exchange_accounts() -> None:
    call = build_ops_call(
        "transfer",
        {
            "mode": "withdraw",
            "token": "usdt",
            "from_exchange": "kc",
            "to_exchange": "bin",
            "amount": 10,
            "missing_fields": [],
        },
    )
    body = (
        '{"code":404,"message":"Transfer account not found",'
        '"request_id":"939f95926043484a892e8518556ccff6"}'
    )

    assert _format_response(call, 200, body) == (
        body
        + '\nkucoin account: ["spotarb", "fdvstrat", "-vefrspot", '
        '"volumenewlisting", "liquidity", "spotinv", "mirroracc2", '
        '"colostrat1", "rfqhedge", "FR2"]'
        + '\nbinance account: ["fr"]'
    )


def test_format_non_json_response_omits_method_and_status() -> None:
    call = build_ops_call("health", {})

    assert _format_response(call, 500, "service unavailable\n") == (
        "service unavailable"
    )


def test_format_non_json_response_strips_ssh_banner() -> None:
    call = build_ops_call("health", {})
    body = """Welcome to Ubuntu 22.04.3 LTS (GNU/Linux 6.5.0-1023-aws x86_64)

 * Documentation:  https://help.ubuntu.com
 * Management:     https://landscape.canonical.com
 * Support:        https://ubuntu.com/advantage

  System information as of Mon May 18 11:17:08 UTC 2026

  System load:  4.82861328125       Processes:             3895
  Usage of /:   92.0% of 968.99GB   Users logged in:       2
  Memory usage: 70%                 IPv4 address for ens5: 172.31.41.68
  Swap usage:   0%

  => / is using 92.0% of 968.99GB

 * Ubuntu Pro delivers the most comprehensive open source security and
   compliance features.

   https://ubuntu.com/aws/pro

Expanded Security Maintenance for Applications is not enabled.

173 updates can be applied immediately.
To see these additional updates run: apt list --upgradable

16 additional security updates can be applied with ESM Apps.
Learn more about enabling ESM Apps service at https://ubuntu.com/esm

New release '24.04.4 LTS' available.
Run 'do-release-upgrade' to upgrade to it.


*** System restart required ***
✅ success
==================================================================
kucoincpp_ATWO_USDT_twkpi_st_1.txtpb.INFO:
NEW_ORDER_STATUS_ACCEPTED = 26
"""

    assert _format_response(call, 200, body) == (
        "✅ success\n"
        "==================================================================\n"
        "kucoincpp_ATWO_USDT_twkpi_st_1.txtpb.INFO:\n"
        "NEW_ORDER_STATUS_ACCEPTED = 26"
    )
