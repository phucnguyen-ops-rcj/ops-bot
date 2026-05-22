from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ops_bot.responses import BotResponse
from ops_bot.settings import app_settings

DEFAULT_PREFECT_SCHEDULE_TEMPLATE = """{
  "symbol": "KAIO",
  "scheduled_time": "2026-05-22 09:30"
}"""

SCHEDULE_VOLUME_TEMPLATE = """{
  "symbol": "KAIO",
  "quote_ccy": "USDT",
  "scheduled_time": "2026-05-22 09:30"
}"""

SCHEDULE_STACKER_TEMPLATE = """{
  "symbol": "BILL",
  "quote_ccy": "USDT",
  "scheduled_time": "2026-05-22 09:30",
  "stacker_interval_minutes": 10
}"""

SCHEDULE_MIRROR_TEMPLATE = """{
  "symbol": "BILL",
  "component": "strategy",
  "method": "start",
  "exchange": "kucoin",
  "market": "spot",
  "quote_ccy": "USDT",
  "scheduled_time": "2026-05-22 09:30"
}"""

SCHEDULE_NEW_LISTING_TEMPLATE = """{
  "symbol": "BILL",
  "scheduled_time": "05:00",
  "quote_ccy": "USDT",
  "stacker_interval_minutes": 10
}"""

REMOVE_SCHEDULES_TEMPLATE = """{
  "flow_run_ids": ["run-1", "run-2"]
}"""

_DEPLOYMENTS: dict[str, tuple[str, str]] = {
    "volume": ("Start Volume Strategy", "volume-start-strategy"),
    "stacker": ("Launch Stacker", "stacker-launch"),
    "mirror": ("Mirror Process Control", "mirror-control"),
}


@dataclass(frozen=True)
class PrefectApiResponse:
    endpoint: str
    status: int
    body: str

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class PrefectApiClient:
    def __init__(
        self,
        api_url: str = app_settings.prefect_api_url,
        timeout_seconds: int = app_settings.prefect_timeout_seconds,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def read_deployment_by_name(self, flow_name: str, deployment_name: str) -> dict[str, Any]:
        flow_segment = urllib.parse.quote(flow_name, safe="")
        deployment_segment = urllib.parse.quote(deployment_name, safe="")
        response = self._request(
            "GET",
            f"/deployments/name/{flow_segment}/{deployment_segment}",
        )
        if not response.ok:
            raise ValueError(_format_prefect_error(response, "deployment lookup failed"))
        return _parse_json_object(response.body, "deployment lookup response")

    def create_flow_run(
        self,
        deployment_id: str,
        *,
        scheduled_time: datetime,
        parameters: dict[str, Any],
        flow_run_name: str = "",
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        flow_run, _ = self.create_flow_run_with_response(
            deployment_id,
            scheduled_time=scheduled_time,
            parameters=parameters,
            flow_run_name=flow_run_name,
            idempotency_key=idempotency_key,
        )
        return flow_run

    def create_flow_run_with_response(
        self,
        deployment_id: str,
        *,
        scheduled_time: datetime,
        parameters: dict[str, Any],
        flow_run_name: str = "",
        idempotency_key: str = "",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        payload: dict[str, Any] = {
            "parameters": parameters,
            "state": {
                "type": "SCHEDULED",
                "state_details": {
                    "scheduled_time": _to_utc_iso(scheduled_time),
                },
            },
        }
        if flow_run_name:
            payload["name"] = flow_run_name
        if idempotency_key:
            payload["idempotency_key"] = idempotency_key
        response = self._request(
            "POST",
            f"/deployments/{deployment_id}/create_flow_run",
            payload,
        )
        if not response.ok:
            raise ValueError(_format_prefect_error(response, "flow run creation failed"))
        parsed = _parse_json_object(response.body, "flow run creation response")
        return parsed, {
            "endpoint": response.endpoint,
            "status": response.status,
            "body": response.body,
        }

    def delete_flow_run(self, flow_run_id: str) -> None:
        _, _ = self.delete_flow_run_with_response(flow_run_id)

    def delete_flow_run_with_response(self, flow_run_id: str) -> tuple[bool, dict[str, Any]]:
        encoded_id = urllib.parse.quote(flow_run_id, safe="")
        response = self._request("DELETE", f"/flow_runs/{encoded_id}")
        if response.status == 404:
            return False, {
                "endpoint": response.endpoint,
                "status": response.status,
                "body": response.body,
            }
        if not response.ok:
            raise ValueError(_format_prefect_error(response, "flow run deletion failed"))
        return True, {
            "endpoint": response.endpoint,
            "status": response.status,
            "body": response.body,
        }

    def _request(
        self,
        method: str,
        endpoint: str,
        payload: dict[str, Any] | None = None,
    ) -> PrefectApiResponse:
        request = urllib.request.Request(
            f"{self.api_url}{endpoint}",
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
                return PrefectApiResponse(endpoint=endpoint, status=response.status, body=body)
        except urllib.error.HTTPError as exc:
            return PrefectApiResponse(
                endpoint=endpoint,
                status=exc.code,
                body=exc.read().decode("utf-8", errors="replace"),
            )


@dataclass(frozen=True)
class VolumeScheduleRequest:
    symbol: str
    quote_ccy: str
    scheduled_time: datetime
    flow_run_name: str
    idempotency_key: str
    execution_mode: str | None
    ssh_host: str | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "VolumeScheduleRequest":
        return cls(
            symbol=_require_text(payload, "symbol").upper(),
            quote_ccy=_optional_text(payload.get("quote_ccy")) or "USDT",
            scheduled_time=_require_scheduled_time(payload),
            flow_run_name=_optional_text(payload.get("flow_run_name")) or "",
            idempotency_key=_optional_text(payload.get("idempotency_key")) or "",
            execution_mode=_optional_text(payload.get("execution_mode")),
            ssh_host=_optional_text(payload.get("ssh_host")),
        )

    def deployment_parameters(self) -> dict[str, Any]:
        parameters: dict[str, Any] = {
            "symbol": self.symbol,
            "quote_ccy": self.quote_ccy.upper(),
        }
        if self.execution_mode:
            parameters["execution_mode"] = self.execution_mode
        if self.ssh_host:
            parameters["ssh_host"] = self.ssh_host
        return parameters


@dataclass(frozen=True)
class StackerScheduleRequest:
    symbol: str
    quote_ccy: str
    scheduled_time: datetime
    stacker_interval_minutes: int
    flow_run_name: str
    idempotency_key: str
    execution_mode: str | None
    ssh_host: str | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "StackerScheduleRequest":
        return cls(
            symbol=_require_text(payload, "symbol").upper(),
            quote_ccy=_optional_text(payload.get("quote_ccy")) or "USDT",
            scheduled_time=_require_scheduled_time(payload),
            stacker_interval_minutes=_positive_int(payload.get("stacker_interval_minutes"), default=10, field_name="stacker_interval_minutes"),
            flow_run_name=_optional_text(payload.get("flow_run_name")) or "",
            idempotency_key=_optional_text(payload.get("idempotency_key")) or "",
            execution_mode=_optional_text(payload.get("execution_mode")),
            ssh_host=_optional_text(payload.get("ssh_host")),
        )

    def deployment_parameters(self, *, stacker_level: int) -> dict[str, Any]:
        parameters: dict[str, Any] = {
            "symbol": self.symbol,
            "stacker_level": stacker_level,
            "quote_ccy": self.quote_ccy.upper(),
        }
        if self.execution_mode:
            parameters["execution_mode"] = self.execution_mode
        if self.ssh_host:
            parameters["ssh_host"] = self.ssh_host
        return parameters


@dataclass(frozen=True)
class MirrorScheduleRequest:
    symbol: str
    component: str
    method: str
    exchange: str
    market: str
    quote_ccy: str
    name_override: str
    scheduled_time: datetime
    flow_run_name: str
    idempotency_key: str
    execution_mode: str | None
    ssh_host: str | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "MirrorScheduleRequest":
        component = (_optional_text(payload.get("component")) or "strategy").lower()
        method = (_optional_text(payload.get("method")) or "start").lower()
        market = (_optional_text(payload.get("market")) or "spot").lower()
        if component not in {"gateway", "feed", "strategy"}:
            raise ValueError("component must be gateway, feed, or strategy.")
        if method not in {"start", "stop", "restart"}:
            raise ValueError("method must be start, stop, or restart.")
        if market not in {"spot", "perp"}:
            raise ValueError("market must be spot or perp.")
        return cls(
            symbol=_require_text(payload, "symbol").upper(),
            component=component,
            method=method,
            exchange=(_optional_text(payload.get("exchange")) or "kucoin").lower(),
            market=market,
            quote_ccy=(_optional_text(payload.get("quote_ccy")) or "USDT").upper(),
            name_override=_optional_text(payload.get("name_override")) or "",
            scheduled_time=_require_scheduled_time(payload),
            flow_run_name=_optional_text(payload.get("flow_run_name")) or "",
            idempotency_key=_optional_text(payload.get("idempotency_key")) or "",
            execution_mode=_optional_text(payload.get("execution_mode")),
            ssh_host=_optional_text(payload.get("ssh_host")),
        )

    def deployment_parameters(self) -> dict[str, Any]:
        parameters: dict[str, Any] = {
            "symbol": self.symbol,
            "component": self.component,
            "method": self.method,
            "name_override": self.name_override,
            "exchange": self.exchange,
            "market": self.market,
            "quote_ccy": self.quote_ccy,
        }
        if self.execution_mode:
            parameters["execution_mode"] = self.execution_mode
        if self.ssh_host:
            parameters["ssh_host"] = self.ssh_host
        return parameters


@dataclass(frozen=True)
class NewListingScheduleRequest:
    symbol: str
    quote_ccy: str
    scheduled_time: datetime
    execution_mode: str | None
    ssh_host: str | None
    stacker_interval_minutes: int
    volume_delay_minutes: int
    mirror_delay_minutes: int
    mirror_component: str
    mirror_method: str
    exchange: str
    market: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "NewListingScheduleRequest":
        stacker_interval_minutes = _optional_int(payload.get("stacker_interval_minutes"), default=10)
        volume_delay_minutes = _optional_int(payload.get("volume_delay_minutes"), default=65)
        mirror_delay_minutes = _optional_int(payload.get("mirror_delay_minutes"), default=120)
        if stacker_interval_minutes <= 0:
            raise ValueError("stacker_interval_minutes must be positive.")
        if volume_delay_minutes <= 0:
            raise ValueError("volume_delay_minutes must be positive.")
        if mirror_delay_minutes <= 0:
            raise ValueError("mirror_delay_minutes must be positive.")
        mirror_component = (_optional_text(payload.get("mirror_component")) or "strategy").lower()
        mirror_method = (_optional_text(payload.get("mirror_method")) or "start").lower()
        market = (_optional_text(payload.get("market")) or "spot").lower()
        if mirror_component not in {"gateway", "feed", "strategy"}:
            raise ValueError("mirror_component must be gateway, feed, or strategy.")
        if mirror_method not in {"start", "stop", "restart"}:
            raise ValueError("mirror_method must be start, stop, or restart.")
        if market not in {"spot", "perp"}:
            raise ValueError("market must be spot or perp.")
        return cls(
            symbol=_require_text(payload, "symbol").upper(),
            quote_ccy=_optional_text(payload.get("quote_ccy")) or "USDT",
            scheduled_time=_require_scheduled_time(payload),
            execution_mode=_optional_text(payload.get("execution_mode")),
            ssh_host=_optional_text(payload.get("ssh_host")),
            stacker_interval_minutes=stacker_interval_minutes,
            volume_delay_minutes=volume_delay_minutes,
            mirror_delay_minutes=mirror_delay_minutes,
            mirror_component=mirror_component,
            mirror_method=mirror_method,
            exchange=(_optional_text(payload.get("exchange")) or "kucoin").lower(),
            market=market,
        )


def schedule_template_for_command(command: str | None) -> str:
    if command == "/schedule-volume":
        return SCHEDULE_VOLUME_TEMPLATE
    if command == "/schedule-mirror":
        return SCHEDULE_MIRROR_TEMPLATE
    if command == "/remove-schedules":
        return REMOVE_SCHEDULES_TEMPLATE
    if command == "/schedule-new-listing":
        return SCHEDULE_NEW_LISTING_TEMPLATE
    if command == "/schedule-stacker":
        return SCHEDULE_STACKER_TEMPLATE
    return DEFAULT_PREFECT_SCHEDULE_TEMPLATE


def handle_schedule_prefect_command(question: str, *, command: str | None) -> BotResponse:
    payload = _extract_json_payload(question)
    schedule_type = _schedule_type_from_command(command)
    try:
        if schedule_type == "remove":
            return _remove_schedules(payload)

        client = PrefectApiClient()
        if schedule_type == "volume":
            request = VolumeScheduleRequest.from_payload(payload)
            record = _create_single_schedule_record(
                client=client,
                schedule_type=schedule_type,
                command=command,
                request=request,
                flow_name=_DEPLOYMENTS["volume"][0],
                deployment_name=_DEPLOYMENTS["volume"][1],
            )
        elif schedule_type == "mirror":
            request = MirrorScheduleRequest.from_payload(payload)
            record = _create_single_schedule_record(
                client=client,
                schedule_type=schedule_type,
                command=command,
                request=request,
                flow_name=_DEPLOYMENTS["mirror"][0],
                deployment_name=_DEPLOYMENTS["mirror"][1],
            )
        elif schedule_type == "new_listing":
            request = NewListingScheduleRequest.from_payload(payload)
            record, prefect_log = _create_new_listing_schedule_record(
                client=client,
                command=command,
                request=request,
            )
        else:
            request = StackerScheduleRequest.from_payload(payload)
            record, prefect_log = _create_stacker_schedule_record(
                client=client,
                command=command,
                request=request,
            )
        if schedule_type in {"volume", "mirror"}:
            prefect_log = record.pop("_prefect_log")
    except ValueError as exc:
        save_schedule_log(
            schedule_type=schedule_type,
            symbol=_optional_text(payload.get("symbol")) or "UNKNOWN",
            payload=payload,
            request_body={"command": command},
            response_body={"error": str(exc)},
        )
        raise

    request_path = save_schedule_request(record)
    state_path = save_schedule_state(record)
    log_path = save_schedule_log(
        schedule_type=record["schedule_type"],
        symbol=record["symbol"],
        payload=payload,
        request_body=record["request_body"],
        response_body={
            "flow_runs": record["flow_runs"],
            "schedule_ref": record["schedule_ref"],
            "prefect_responses": prefect_log,
        },
    )
    message = _build_schedule_message(record)
    return BotResponse(message=message, attachments=(request_path, state_path))


def save_schedule_request(record: dict[str, Any]) -> Path:
    config_dir = app_settings.prefect_schedule_config_dir
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / f"{record['schedule_type']}_{record['symbol'].upper()}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def save_schedule_state(record: dict[str, Any]) -> Path:
    state_dir = app_settings.prefect_schedule_state_dir
    state_dir.mkdir(parents=True, exist_ok=True)
    ref_path = _schedule_ref_path(record["schedule_ref"])
    ref_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    latest_path = _latest_schedule_path(record["schedule_type"], record["symbol"])
    latest_path.write_text(
        json.dumps({"schedule_ref": record["schedule_ref"]}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return ref_path


def save_schedule_log(
    *,
    schedule_type: str,
    symbol: str,
    payload: dict[str, Any],
    request_body: dict[str, Any],
    response_body: dict[str, Any],
) -> Path:
    log_dir = app_settings.prefect_schedule_logs_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _now_utc().strftime("%Y%m%d_%H%M%SZ")
    path = log_dir / f"{schedule_type}_{symbol.upper()}_{timestamp}.log"
    lines = [
        f"timestamp_utc: {_now_utc().isoformat()}",
        "payload:",
        json.dumps(payload, indent=2, sort_keys=True),
        "request_body:",
        json.dumps(request_body, indent=2, sort_keys=True),
        "response_body:",
        json.dumps(response_body, indent=2, sort_keys=True),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _remove_schedules(payload: dict[str, Any]) -> BotResponse:
    flow_run_ids = _required_flow_run_ids(payload)
    client = PrefectApiClient()
    removed: list[dict[str, Any]] = []
    prefect_responses: list[dict[str, Any]] = []
    for flow_run_id in flow_run_ids:
        deleted, prefect_response = client.delete_flow_run_with_response(flow_run_id)
        removed.append({"id": flow_run_id})
        prefect_responses.append(
            {
                "flow_run_id": flow_run_id,
                "deleted": deleted,
                "prefect_response": prefect_response,
            }
        )
    log_path = save_schedule_log(
        schedule_type="remove",
        symbol="FLOW_RUNS",
        payload=payload,
        request_body={"flow_run_ids": flow_run_ids},
        response_body={"removed_runs": removed, "prefect_responses": prefect_responses},
    )
    lines = [
        "Removed scheduled Prefect runs.",
        f"removed_runs: {len(removed)}",
    ]
    for index, item in enumerate(removed, start=1):
        lines.append(f"{index}. run_id={item['id']}")
    return BotResponse(message="\n".join(lines))


def _build_schedule_message(record: dict[str, Any]) -> str:
    flow_run_ids = [flow_run["id"] for flow_run in record["flow_runs"] if flow_run.get("id")]
    lines = [
        f"Created scheduled Prefect runs for `{record['schedule_type']}`.",
        f"schedule_ref: {record['schedule_ref']}",
        f"symbol: {record['symbol']}",
        f"requested_time: {record['requested_time_local']} ({app_settings.prefect_timezone})",
    ]
    if flow_run_ids:
        lines.extend(
            [
                "flow_run_ids:",
                json.dumps(flow_run_ids, ensure_ascii=False),
            ]
        )
    if record["schedule_type"] == "stacker" and len(record["flow_runs"]) == 4:
        interval = record.get("stacker_interval_minutes", 10)
        lines.append(f"Created 4 one-time stacker runs at {interval}-minute intervals for levels 1 to 4.")
    if record["schedule_type"] == "new_listing":
        lines.append("Created stacker levels 1-4, then volume, then mirror based on the requested start time.")
    for index, flow_run in enumerate(record["flow_runs"], start=1):
        line = f"{index}. run_id={flow_run.get('id')} kind={flow_run.get('kind')} state={flow_run.get('state_type')}"
        if flow_run.get("stacker_level") is not None:
            line += f" level={flow_run['stacker_level']}"
        if flow_run.get("scheduled_time"):
            line += f" time={flow_run['scheduled_time']}"
        lines.append(line)
        if app_settings.prefect_ui_url and flow_run.get("id"):
            lines.append(
                f"   {app_settings.prefect_ui_url.rstrip('/')}/flow-runs/flow-run/{flow_run['id']}"
            )
    return "\n".join(lines)


def _create_single_schedule_record(
    *,
    client: PrefectApiClient,
    schedule_type: str,
    command: str | None,
    request: VolumeScheduleRequest | MirrorScheduleRequest,
    flow_name: str,
    deployment_name: str,
) -> dict[str, Any]:
    deployment = client.read_deployment_by_name(flow_name, deployment_name)
    deployment_id = _require_text(deployment, "id")
    parameters = request.deployment_parameters()
    flow_run, prefect_response = client.create_flow_run_with_response(
        deployment_id,
        scheduled_time=request.scheduled_time,
        parameters=parameters,
        flow_run_name=request.flow_run_name,
        idempotency_key=request.idempotency_key,
    )
    flow_runs = [
        _augment_flow_run(
            flow_run,
            kind=schedule_type,
            deployment_name=deployment_name,
            scheduled_time=request.scheduled_time,
        )
    ]
    record = _build_record(
        schedule_type=schedule_type,
        command=command,
        symbol=request.symbol,
        requested_time=request.scheduled_time,
        request_body={
            "deployments": [
                {
                    "deployment_name": deployment_name,
                    "deployment_id": deployment_id,
                    "parameters": parameters,
                    "scheduled_time": request.scheduled_time.isoformat(),
                }
            ]
        },
        flow_runs=flow_runs,
    )
    record["_prefect_log"] = [
        {
            "kind": schedule_type,
            "deployment_name": deployment_name,
            "flow_run_id": flow_run.get("id"),
            "prefect_response": prefect_response,
        }
    ]
    return record


def _create_stacker_schedule_record(
    *,
    client: PrefectApiClient,
    command: str | None,
    request: StackerScheduleRequest,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    flow_name, deployment_name = _DEPLOYMENTS["stacker"]
    deployment = client.read_deployment_by_name(flow_name, deployment_name)
    deployment_id = _require_text(deployment, "id")
    levels = [1, 2, 3, 4]
    interval_minutes = request.stacker_interval_minutes
    flow_runs: list[dict[str, Any]] = []
    deployments: list[dict[str, Any]] = []
    prefect_log: list[dict[str, Any]] = []
    for offset, level in enumerate(levels):
        scheduled_time = request.scheduled_time + timedelta(minutes=offset * interval_minutes)
        parameters = request.deployment_parameters(stacker_level=level)
        flow_run, prefect_response = client.create_flow_run_with_response(
            deployment_id,
            scheduled_time=scheduled_time,
            parameters=parameters,
            flow_run_name=_stacker_flow_run_name(request, level=level, batch=len(levels) > 1),
            idempotency_key=_stacker_idempotency_key(request, level=level, batch=len(levels) > 1),
        )
        flow_runs.append(
            _augment_flow_run(
                flow_run,
                kind="stacker",
                deployment_name=deployment_name,
                scheduled_time=scheduled_time,
                stacker_level=level,
            )
        )
        deployments.append(
            {
                "deployment_name": deployment_name,
                "deployment_id": deployment_id,
                "parameters": parameters,
                "scheduled_time": scheduled_time.isoformat(),
                "stacker_level": level,
            }
        )
        prefect_log.append(
            {
                "kind": "stacker",
                "deployment_name": deployment_name,
                "flow_run_id": flow_run.get("id"),
                "stacker_level": level,
                "prefect_response": prefect_response,
            }
        )
    return _build_record(
        schedule_type="stacker",
        command=command,
        symbol=request.symbol,
        requested_time=request.scheduled_time,
        request_body={"deployments": deployments},
        flow_runs=flow_runs,
        extra={"stacker_interval_minutes": interval_minutes},
    ), prefect_log


def _create_new_listing_schedule_record(
    *,
    client: PrefectApiClient,
    command: str | None,
    request: NewListingScheduleRequest,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    stacker_flow_name, stacker_deployment_name = _DEPLOYMENTS["stacker"]
    volume_flow_name, volume_deployment_name = _DEPLOYMENTS["volume"]
    mirror_flow_name, mirror_deployment_name = _DEPLOYMENTS["mirror"]

    stacker_deployment_id = _require_text(
        client.read_deployment_by_name(stacker_flow_name, stacker_deployment_name),
        "id",
    )
    volume_deployment_id = _require_text(
        client.read_deployment_by_name(volume_flow_name, volume_deployment_name),
        "id",
    )
    mirror_deployment_id = _require_text(
        client.read_deployment_by_name(mirror_flow_name, mirror_deployment_name),
        "id",
    )

    flow_runs: list[dict[str, Any]] = []
    deployments: list[dict[str, Any]] = []
    prefect_log: list[dict[str, Any]] = []
    for level in (1, 2, 3, 4):
        scheduled_time = request.scheduled_time + timedelta(
            minutes=(level - 1) * request.stacker_interval_minutes
        )
        parameters = {
            "symbol": request.symbol,
            "stacker_level": level,
            "quote_ccy": request.quote_ccy.upper(),
        }
        if request.execution_mode:
            parameters["execution_mode"] = request.execution_mode
        if request.ssh_host:
            parameters["ssh_host"] = request.ssh_host
        flow_run, prefect_response = client.create_flow_run_with_response(
            stacker_deployment_id,
            scheduled_time=scheduled_time,
            parameters=parameters,
        )
        flow_runs.append(
            _augment_flow_run(
                flow_run,
                kind="stacker",
                deployment_name=stacker_deployment_name,
                scheduled_time=scheduled_time,
                stacker_level=level,
            )
        )
        deployments.append(
            {
                "deployment_name": stacker_deployment_name,
                "deployment_id": stacker_deployment_id,
                "parameters": parameters,
                "scheduled_time": scheduled_time.isoformat(),
                "stacker_level": level,
            }
        )
        prefect_log.append(
            {
                "kind": "stacker",
                "deployment_name": stacker_deployment_name,
                "flow_run_id": flow_run.get("id"),
                "stacker_level": level,
                "prefect_response": prefect_response,
            }
        )

    volume_time = request.scheduled_time + timedelta(minutes=request.volume_delay_minutes)
    volume_parameters: dict[str, Any] = {
        "symbol": request.symbol,
        "quote_ccy": request.quote_ccy.upper(),
    }
    if request.execution_mode:
        volume_parameters["execution_mode"] = request.execution_mode
    if request.ssh_host:
        volume_parameters["ssh_host"] = request.ssh_host
    volume_run, volume_response = client.create_flow_run_with_response(
        volume_deployment_id,
        scheduled_time=volume_time,
        parameters=volume_parameters,
    )
    flow_runs.append(
        _augment_flow_run(
            volume_run,
            kind="volume",
            deployment_name=volume_deployment_name,
            scheduled_time=volume_time,
        )
    )
    deployments.append(
        {
            "deployment_name": volume_deployment_name,
            "deployment_id": volume_deployment_id,
            "parameters": volume_parameters,
            "scheduled_time": volume_time.isoformat(),
        }
    )
    prefect_log.append(
        {
            "kind": "volume",
            "deployment_name": volume_deployment_name,
            "flow_run_id": volume_run.get("id"),
            "prefect_response": volume_response,
        }
    )

    mirror_time = request.scheduled_time + timedelta(minutes=request.mirror_delay_minutes)
    mirror_parameters: dict[str, Any] = {
        "symbol": request.symbol,
        "component": request.mirror_component,
        "method": request.mirror_method,
        "name_override": "",
        "exchange": request.exchange,
        "market": request.market,
        "quote_ccy": request.quote_ccy.upper(),
    }
    if request.execution_mode:
        mirror_parameters["execution_mode"] = request.execution_mode
    if request.ssh_host:
        mirror_parameters["ssh_host"] = request.ssh_host
    mirror_run, mirror_response = client.create_flow_run_with_response(
        mirror_deployment_id,
        scheduled_time=mirror_time,
        parameters=mirror_parameters,
    )
    flow_runs.append(
        _augment_flow_run(
            mirror_run,
            kind="mirror",
            deployment_name=mirror_deployment_name,
            scheduled_time=mirror_time,
        )
    )
    deployments.append(
        {
            "deployment_name": mirror_deployment_name,
            "deployment_id": mirror_deployment_id,
            "parameters": mirror_parameters,
            "scheduled_time": mirror_time.isoformat(),
        }
    )
    prefect_log.append(
        {
            "kind": "mirror",
            "deployment_name": mirror_deployment_name,
            "flow_run_id": mirror_run.get("id"),
            "prefect_response": mirror_response,
        }
    )

    return _build_record(
        schedule_type="new_listing",
        command=command,
        symbol=request.symbol,
        requested_time=request.scheduled_time,
        request_body={"deployments": deployments},
        flow_runs=flow_runs,
        extra={"stacker_interval_minutes": request.stacker_interval_minutes},
    ), prefect_log


def _build_record(
    *,
    schedule_type: str,
    command: str | None,
    symbol: str,
    requested_time: datetime,
    request_body: dict[str, Any],
    flow_runs: list[dict[str, Any]],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    schedule_ref = _make_schedule_ref(schedule_type, symbol, requested_time)
    record = {
        "schedule_ref": schedule_ref,
        "schedule_type": schedule_type,
        "command": command,
        "symbol": symbol,
        "requested_time_local": _format_local_time(requested_time),
        "requested_time_utc": _to_utc_iso(requested_time),
        "created_at": _now_utc().isoformat(),
        "request_body": request_body,
        "flow_runs": flow_runs,
    }
    if extra:
        record.update(extra)
    return record


def _augment_flow_run(
    flow_run: dict[str, Any],
    *,
    kind: str,
    deployment_name: str,
    scheduled_time: datetime,
    stacker_level: int | None = None,
) -> dict[str, Any]:
    updated = dict(flow_run)
    updated["kind"] = kind
    updated["deployment_name"] = deployment_name
    updated["scheduled_time"] = _format_local_time(scheduled_time)
    if stacker_level is not None:
        updated["stacker_level"] = stacker_level
    return updated


def _schedule_type_from_command(command: str | None) -> str:
    if command == "/schedule-volume":
        return "volume"
    if command == "/schedule-mirror":
        return "mirror"
    if command == "/schedule-new-listing":
        return "new_listing"
    if command == "/remove-schedules":
        return "remove"
    return "stacker"


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
        raise ValueError("Schedule payload must be a JSON object.")
    return payload


def _require_scheduled_time(payload: dict[str, Any]) -> datetime:
    raw_value = _require_text(payload, "scheduled_time")
    scheduled_time = _parse_scheduled_time(raw_value)
    if scheduled_time <= _now_utc():
        raise ValueError("scheduled_time must be in the future.")
    return scheduled_time


def _parse_scheduled_time(raw_value: str) -> datetime:
    normalized = raw_value.strip()
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        return _apply_default_timezone(parsed)
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return _apply_default_timezone(datetime.strptime(normalized, fmt))
        except ValueError:
            continue

    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            parsed_time = datetime.strptime(normalized, fmt)
        except ValueError:
            continue
        local_now = _now_local()
        candidate = local_now.replace(
            hour=parsed_time.hour,
            minute=parsed_time.minute,
            second=parsed_time.second,
            microsecond=0,
        )
        if candidate <= local_now:
            candidate += timedelta(days=1)
        return candidate

    raise ValueError(
        "scheduled_time must be like `05:00`, `2026-05-22 09:30`, or full ISO 8601."
    )


def _apply_default_timezone(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value
    return value.replace(tzinfo=_prefect_zone())


def _schedule_ref_path(schedule_ref: str) -> Path:
    state_dir = app_settings.prefect_schedule_state_dir
    state_dir.mkdir(parents=True, exist_ok=True)
    safe_ref = re.sub(r"[^A-Za-z0-9_.-]+", "_", schedule_ref)
    return state_dir / f"{safe_ref}.json"


def _latest_schedule_path(schedule_type: str, symbol: str) -> Path:
    state_dir = app_settings.prefect_schedule_state_dir
    state_dir.mkdir(parents=True, exist_ok=True)
    safe_symbol = re.sub(r"[^A-Za-z0-9_.-]+", "_", symbol.upper())
    return state_dir / f"latest_{schedule_type}_{safe_symbol}.json"


def _make_schedule_ref(schedule_type: str, symbol: str, scheduled_time: datetime) -> str:
    local_stamp = scheduled_time.astimezone(_prefect_zone()).strftime("%Y%m%dT%H%M%S")
    created_stamp = _now_utc().strftime("%H%M%S")
    return f"{schedule_type}-{symbol.upper()}-{local_stamp}-{created_stamp}"


def _require_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if value is None:
        raise ValueError(f"Missing required field: {key}")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"Missing required field: {key}")
    return normalized


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_int(value: object, *, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Interval fields must be integers.") from exc


def _positive_int(value: object, *, default: int, field_name: str) -> int:
    parsed = _optional_int(value, default=default)
    if parsed <= 0:
        raise ValueError(f"{field_name} must be positive.")
    return parsed


def _required_flow_run_ids(payload: dict[str, Any]) -> list[str]:
    single = _optional_text(payload.get("flow_run_id"))
    if single:
        return [single]

    value = payload.get("flow_run_ids")
    if value is None:
        raise ValueError("Provide flow_run_id or flow_run_ids.")
    if not isinstance(value, list):
        raise ValueError("flow_run_ids must be a JSON array of strings.")

    ids: list[str] = []
    for item in value:
        normalized = str(item).strip()
        if not normalized:
            raise ValueError("flow_run_ids cannot contain empty values.")
        ids.append(normalized)
    return ids


def _parse_json_object(value: str, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid {label}: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be a JSON object.")
    return parsed


def _format_prefect_error(response: PrefectApiResponse, fallback: str) -> str:
    body = response.body.strip()
    if not body:
        return f"{fallback} with HTTP {response.status}."
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return f"{fallback} with HTTP {response.status}: {body}"
    if isinstance(parsed, dict):
        detail = parsed.get("detail")
        if isinstance(detail, str) and detail.strip():
            return f"{fallback} with HTTP {response.status}: {detail.strip()}"
    compact = re.sub(r"\s+", " ", body)
    return f"{fallback} with HTTP {response.status}: {compact}"


def _stacker_flow_run_name(request: StackerScheduleRequest, *, level: int, batch: bool) -> str:
    if not request.flow_run_name:
        return ""
    if batch:
        return f"{request.flow_run_name}-l{level}"
    return request.flow_run_name


def _stacker_idempotency_key(request: StackerScheduleRequest, *, level: int, batch: bool) -> str:
    if not request.idempotency_key:
        return ""
    if batch:
        return f"{request.idempotency_key}-l{level}"
    return request.idempotency_key


def _format_local_time(value: datetime) -> str:
    return value.astimezone(_prefect_zone()).strftime("%Y-%m-%d %H:%M")


def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _prefect_zone() -> ZoneInfo:
    try:
        return ZoneInfo(app_settings.prefect_timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Invalid prefect timezone: {app_settings.prefect_timezone}") from exc


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_local() -> datetime:
    return _now_utc().astimezone(_prefect_zone())
