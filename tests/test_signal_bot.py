from __future__ import annotations

from pathlib import Path

from ops_bot.responses import BotResponse
from ops_bot.scripts import signal_bot


def _payload(message: str, group_id: str | None = None) -> dict:
    data_message: dict = {"message": message}
    if group_id:
        data_message["groupInfo"] = {"groupId": group_id}
    return {
        "envelope": {
            "source": "+15550001111",
            "dataMessage": data_message,
        }
    }


def test_individual_message_does_not_need_mention() -> None:
    assert signal_bot._text_for_handling(_payload("withdraw 10 usdt")) == (
        "withdraw 10 usdt"
    )


def test_group_message_without_mention_is_ignored(monkeypatch) -> None:
    monkeypatch.setattr(signal_bot.app_settings, "signal_bot_mention_aliases", "opsbot")

    assert signal_bot._text_for_handling(
        _payload("withdraw 10 usdt", group_id="group.123")
    ) is None


def test_group_message_with_text_mention_is_stripped(monkeypatch) -> None:
    monkeypatch.setattr(signal_bot.app_settings, "signal_bot_mention_aliases", "opsbot")

    assert signal_bot._text_for_handling(
        _payload("@opsbot /transfer withdraw 10 usdt", group_id="group.123")
    ) == "/transfer withdraw 10 usdt"


def test_group_message_with_metadata_mention_is_handled(monkeypatch) -> None:
    monkeypatch.setattr(signal_bot.app_settings, "signal_sender", "+15550002222")
    payload = _payload("withdraw 10 usdt", group_id="group.123")
    payload["envelope"]["dataMessage"]["mentions"] = [
        {"author": "+15550002222", "start": 0, "length": 6}
    ]

    assert signal_bot._text_for_handling(payload) == "withdraw 10 usdt"


def test_reply_target_uses_sendable_group_id_from_payload() -> None:
    assert signal_bot._reply_target(_payload("ok", group_id="group.123")) == {
        "recipient": None,
        "group_id": "group.123",
    }


def test_send_reply_passes_attachments(monkeypatch, tmp_path) -> None:
    sent: dict = {}
    attachment = tmp_path / "config.json"
    attachment.write_text("{}", encoding="utf-8")

    def fake_send(
        _self,
        message,
        *,
        attachments=None,
        recipient=None,
        group_id=None,
    ) -> dict:
        sent["message"] = message
        sent["attachments"] = attachments
        sent["recipient"] = recipient
        sent["group_id"] = group_id
        return {"success": True}

    monkeypatch.setattr(signal_bot.SignalClient, "send", fake_send)

    signal_bot._send_reply(
        BotResponse(message="done", attachments=(attachment,)),
        _payload("ok"),
    )

    assert sent["message"] == "done"
    assert sent["attachments"] == (attachment,)


def test_reply_target_uses_configured_group_id_for_receive_only_group_id(
    monkeypatch,
) -> None:
    monkeypatch.setattr(signal_bot.SignalClient, "list_groups", lambda _self: [])
    monkeypatch.setattr(signal_bot.app_settings, "signal_group_id", "group.configured")
    payload = _payload("ok", group_id="raw-receive-group-id")

    assert signal_bot._reply_target(payload) == {
        "recipient": None,
        "group_id": "group.configured",
    }


def test_reply_target_skips_group_without_sendable_group_id(monkeypatch) -> None:
    monkeypatch.setattr(signal_bot.SignalClient, "list_groups", lambda _self: [])
    monkeypatch.setattr(signal_bot.app_settings, "signal_group_id", "")
    payload = _payload("ok", group_id="raw-receive-group-id")

    assert signal_bot._reply_target(payload) == {
        "recipient": None,
        "group_id": None,
    }


def test_reply_target_refreshes_and_saves_group_id_cache(
    monkeypatch,
    tmp_path,
) -> None:
    calls = 0

    def list_groups(_self) -> list[dict]:
        nonlocal calls
        calls += 1
        return [
            {
                "id": "group.sendable",
                "internal_id": "raw-receive-group-id",
                "name": "Ops",
            }
        ]

    monkeypatch.setattr(signal_bot.SignalClient, "list_groups", list_groups)
    monkeypatch.setattr(signal_bot.app_settings, "signal_group_id", "")
    monkeypatch.setattr(
        signal_bot.app_settings,
        "signal_group_cache_path",
        tmp_path / "signal_groups.yml",
    )

    payload = _payload("ok", group_id="raw-receive-group-id")

    assert signal_bot._reply_target(payload) == {
        "recipient": None,
        "group_id": "group.sendable",
    }
    assert calls == 1
    assert "raw-receive-group-id" in (
        tmp_path / "signal_groups.yml"
    ).read_text(encoding="utf-8")

    assert signal_bot._reply_target(payload) == {
        "recipient": None,
        "group_id": "group.sendable",
    }
    assert calls == 1


def test_real_signal_group_payload_maps_internal_id_to_sendable_id(
    monkeypatch,
    tmp_path,
) -> None:
    groups = [
        {
            "name": "Phuc Training",
            "id": "group.ZEFBVWtxRGNHTm90WDUwdWhxcjc3SE0rYnJxOFk4L1RMWFdxNFhmMW9mZz0=",
            "internal_id": "dAAUkqDcGNotX50uhqr77HM+brq8Y8/TLXWq4Xf1ofg=",
        },
        {
            "name": "Tessting",
            "id": "group.OFpmdUlZYWZlV2J4QTdBZ2hWYmdoTk5KeUpQcHh4R3VVS3FwZjhEaDRVST0=",
            "internal_id": "8ZfuIYafeWbxA7AghVbghNNJyJPpxxGuUKqpf8Dh4UI=",
        },
    ]

    monkeypatch.setattr(signal_bot.SignalClient, "list_groups", lambda _self: groups)
    monkeypatch.setattr(signal_bot.app_settings, "signal_sender", "+84559854979")
    monkeypatch.setattr(signal_bot.app_settings, "signal_group_id", "")
    monkeypatch.setattr(
        signal_bot.app_settings,
        "signal_group_cache_path",
        tmp_path / "signal_groups.yml",
    )
    payload = {
        "envelope": {
            "source": "+84906303607",
            "dataMessage": {
                "message": "\ufffc hello",
                "mentions": [
                    {
                        "name": "+84559854979",
                        "number": "+84559854979",
                        "uuid": "eaa33ccc-d633-4ba5-a2f4-33cf1aaaab8b",
                        "start": 0,
                        "length": 1,
                    }
                ],
                "groupInfo": {
                    "groupId": "8ZfuIYafeWbxA7AghVbghNNJyJPpxxGuUKqpf8Dh4UI=",
                    "groupName": "Tessting",
                    "revision": 1,
                    "type": "DELIVER",
                },
            },
        }
    }

    assert signal_bot._text_for_handling(payload) == "hello"
    assert signal_bot._reply_target(payload) == {
        "recipient": None,
        "group_id": "group.OFpmdUlZYWZlV2J4QTdBZ2hWYmdoTk5KeUpQcHh4R3VVS3FwZjhEaDRVST0=",
    }
