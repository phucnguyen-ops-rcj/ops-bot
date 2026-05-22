from __future__ import annotations

import asyncio
import json
from pathlib import Path

from ops_bot.responses import BotResponse
from ops_bot.service import handle_user_message


def test_schedule_volume_template_response() -> None:
    response = asyncio.run(handle_user_message("/schedule-volume"))

    assert isinstance(response, str)
    assert '"symbol": "KAIO"' in response
    assert '"scheduled_time": "2026-05-22 09:30"' in response
    assert '"shutdown"' not in response


def test_remove_schedules_template_response() -> None:
    response = asyncio.run(handle_user_message("/remove-schedules"))

    assert isinstance(response, str)
    assert '"flow_run_ids": ["run-1", "run-2"]' in response


def test_schedule_stacker_batch_run(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "prefect_schedules" / "config"
    logs_dir = tmp_path / "prefect_schedules" / "logs"
    state_dir = tmp_path / "prefect_schedules" / "state"
    monkeypatch.setattr(
        "ops_bot.prefect_schedules.bot_service.app_settings.prefect_schedule_config_dir",
        config_dir,
    )
    monkeypatch.setattr(
        "ops_bot.prefect_schedules.bot_service.app_settings.prefect_schedule_logs_dir",
        logs_dir,
    )
    monkeypatch.setattr(
        "ops_bot.prefect_schedules.bot_service.app_settings.prefect_schedule_state_dir",
        state_dir,
    )
    monkeypatch.setattr(
        "ops_bot.prefect_schedules.bot_service.app_settings.prefect_ui_url",
        "http://prefect.test:4200",
    )

    calls: list[dict[str, object]] = []

    class FakePrefectApiClient:
        def read_deployment_by_name(self, flow_name: str, deployment_name: str) -> dict[str, str]:
            assert flow_name == "Launch Stacker"
            assert deployment_name == "stacker-launch"
            return {"id": "deployment-123"}

        def create_flow_run(
            self,
            deployment_id: str,
            *,
            scheduled_time,
            parameters,
            flow_run_name: str = "",
            idempotency_key: str = "",
        ) -> dict[str, object]:
            calls.append(
                {
                    "deployment_id": deployment_id,
                    "scheduled_time": scheduled_time.strftime("%Y-%m-%d %H:%M"),
                    "parameters": parameters,
                }
            )
            level = parameters["stacker_level"]
            return {
                "id": f"flow-run-{level}",
                "state_type": "SCHEDULED",
            }

    monkeypatch.setattr(
        "ops_bot.prefect_schedules.bot_service.PrefectApiClient",
        FakePrefectApiClient,
    )

    response = asyncio.run(
        handle_user_message(
            """/schedule-stacker
{
  "symbol": "BILL",
  "scheduled_time": "2099-05-22 09:30",
  "stacker_interval_minutes": 7
}"""
        )
    )

    assert isinstance(response, BotResponse)
    assert len(calls) == 4
    assert [call["parameters"]["stacker_level"] for call in calls] == [1, 2, 3, 4]
    assert [call["scheduled_time"] for call in calls] == [
        "2099-05-22 09:30",
        "2099-05-22 09:37",
        "2099-05-22 09:44",
        "2099-05-22 09:51",
    ]
    assert "Created 4 one-time stacker runs at 7-minute intervals for levels 1 to 4." in response.message
    assert "level=1" in response.message
    assert "level=4" in response.message
    assert len(response.attachments) == 2

    request_path = config_dir / "stacker_BILL.json"
    assert request_path.exists()
    saved_request = json.loads(request_path.read_text(encoding="utf-8"))
    assert saved_request["stacker_interval_minutes"] == 7


def test_schedule_new_listing_creates_staggered_runs(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "prefect_schedules" / "config"
    logs_dir = tmp_path / "prefect_schedules" / "logs"
    state_dir = tmp_path / "prefect_schedules" / "state"
    monkeypatch.setattr(
        "ops_bot.prefect_schedules.bot_service.app_settings.prefect_schedule_config_dir",
        config_dir,
    )
    monkeypatch.setattr(
        "ops_bot.prefect_schedules.bot_service.app_settings.prefect_schedule_logs_dir",
        logs_dir,
    )
    monkeypatch.setattr(
        "ops_bot.prefect_schedules.bot_service.app_settings.prefect_schedule_state_dir",
        state_dir,
    )

    calls: list[dict[str, object]] = []

    class FakePrefectApiClient:
        def read_deployment_by_name(self, flow_name: str, deployment_name: str) -> dict[str, str]:
            return {"id": f"{deployment_name}-id"}

        def create_flow_run(
            self,
            deployment_id: str,
            *,
            scheduled_time,
            parameters,
            flow_run_name: str = "",
            idempotency_key: str = "",
        ) -> dict[str, object]:
            calls.append(
                {
                    "deployment_id": deployment_id,
                    "scheduled_time": scheduled_time.strftime("%Y-%m-%d %H:%M"),
                    "parameters": parameters,
                }
            )
            return {
                "id": f"run-{len(calls)}",
                "state_type": "SCHEDULED",
            }

    monkeypatch.setattr(
        "ops_bot.prefect_schedules.bot_service.PrefectApiClient",
        FakePrefectApiClient,
    )

    response = asyncio.run(
        handle_user_message(
            """/schedule-new-listing
{
  "symbol": "BILL",
  "scheduled_time": "2099-05-22 05:00"
}"""
        )
    )

    assert isinstance(response, BotResponse)
    assert len(calls) == 6
    assert [call["scheduled_time"] for call in calls] == [
        "2099-05-22 05:00",
        "2099-05-22 05:10",
        "2099-05-22 05:20",
        "2099-05-22 05:30",
        "2099-05-22 06:05",
        "2099-05-22 07:00",
    ]
    assert [call["parameters"].get("stacker_level") for call in calls[:4]] == [1, 2, 3, 4]
    assert "kind=volume" in response.message
    assert "kind=mirror" in response.message


def test_remove_schedules_accepts_explicit_flow_run_ids(monkeypatch, tmp_path: Path) -> None:
    logs_dir = tmp_path / "prefect_schedules" / "logs"
    monkeypatch.setattr(
        "ops_bot.prefect_schedules.bot_service.app_settings.prefect_schedule_logs_dir",
        logs_dir,
    )

    deleted: list[str] = []

    class FakePrefectApiClient:
        def delete_flow_run(self, flow_run_id: str) -> None:
            deleted.append(flow_run_id)

    monkeypatch.setattr(
        "ops_bot.prefect_schedules.bot_service.PrefectApiClient",
        FakePrefectApiClient,
    )

    response = asyncio.run(
        handle_user_message(
            """/remove-schedules
{
  "flow_run_ids": ["run-1", "run-2", "run-3"]
}"""
        )
    )

    assert isinstance(response, BotResponse)
    assert deleted == ["run-1", "run-2", "run-3"]
    assert "Removed scheduled Prefect runs." in response.message
    assert "removed_runs: 3" in response.message
    assert "run_id=run-1" in response.message
    assert response.attachments == ()


def test_schedule_rejects_past_time() -> None:
    response = asyncio.run(
        handle_user_message(
            """/schedule-volume
{
  "symbol": "KAIO",
  "scheduled_time": "2020-05-22 09:30"
}"""
        )
    )

    assert response == "scheduled_time must be in the future."
