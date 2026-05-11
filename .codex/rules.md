# Ops Bot Codex Rules

## Project

This repository is a standalone Signal bot for RCJ ops API commands.
Signal messages are received through `signal-cli-rest-api`, routed to one of
the supported command agents, extracted into typed parameters by BAML,
validated in Python, sent to the RCJ ops API, and answered back through Signal.

## Architecture Boundaries

- Keep this repo independent from `../reports`; do not import reports code.
- Keep BAML limited to structured parameter extraction.
- Do not let BAML choose runtime behavior, execute commands, or generate curl.
- Keep routing, validation, API request construction, API calls, and Signal
  replies in Python.
- Prefer deterministic slash-command routing over keyword routing when adding
  or changing command behavior.
- If required request data is missing, ask a clear follow-up question instead
  of calling the ops API.
- Treat transfers as sensitive operations. Keep transfer validation explicit,
  conservative, and easy to test.

## Commands

Use `uv` for project commands:

```bash
uv sync
uv run baml-cli generate
uv run signal_bot
uv run pytest
uv run pytest tests/test_ops_bot.py
```

When changing `baml_src/`, regenerate and keep matching `src/baml_client/`
changes together.

## Testing

- Keep unit tests deterministic.
- Do not call real Signal, LLM, or RCJ ops API services in unit tests.
- Focus tests on routing, validation, and request construction.
- Mark integration tests explicitly if a real external service is required.

## Logging And Settings

- Configure logging only in entry-point `main()` functions.
- Use `logging.getLogger(__name__)` in utility modules.
- Keep secrets in environment variables or service-manager configuration, not
  committed files.
