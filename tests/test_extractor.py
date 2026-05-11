from __future__ import annotations

import os
from types import SimpleNamespace

from ops_bot import extractor


def test_baml_options_use_openai_key_from_settings(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        extractor,
        "get_settings",
        lambda: SimpleNamespace(openai_api_key="sk-from-settings"),
    )

    options = extractor._baml_options()

    assert "client_registry" in options
    assert "OPENAI_API_KEY" not in os.environ
