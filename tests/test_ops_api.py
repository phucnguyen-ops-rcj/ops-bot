from __future__ import annotations

from types import SimpleNamespace

from ops_bot.clients.ops_api import OpsApiClient


class _FakeHttpResponse:
    def __init__(self, body: str, status: int = 200) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body.encode("utf-8")

    def __enter__(self) -> "_FakeHttpResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_ops_api_request_appends_shared_log(monkeypatch, tmp_path) -> None:
    log_path = tmp_path / "ops_api.log"
    monkeypatch.setattr(
        "ops-bot.clients.ops_api.get_settings",
        lambda: SimpleNamespace(
            rcj_ops_bearer_token="token",
            ops_api_log_path=log_path,
        ),
    )
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: _FakeHttpResponse('{"ok":true}', status=200),
    )

    client = OpsApiClient(
        base_endpoint="http://example.com",
        timeout_seconds=5,
        execution_mode="local",
    )
    response = client.post("/health", {"symbol": "KAIO-USDT"})

    assert response.status == 200
    assert response.body == '{"ok":true}'
    log_text = log_path.read_text(encoding="utf-8")
    assert "method: POST" in log_text
    assert "endpoint: /health" in log_text
    assert "execution_mode: local" in log_text
    assert '"symbol": "KAIO-USDT"' in log_text
    assert "output:" in log_text
    assert '{"ok":true}' in log_text
