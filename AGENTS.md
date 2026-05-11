# Codex Project Instructions

This repository is a standalone Signal bot for the RCJ ops API.

## Architecture

1. `ops_bot.scripts.signal_bot` receives Signal messages through
   `signal-cli-rest-api` using auto-detected HTTP polling or WebSocket receive.
2. `ops_bot.routing` chooses one of four supported agents: `health`, `balance`,
   `transfer`, or `monitor`.
3. BAML functions in `baml_src/ops_bot.baml` extract typed parameters only.
4. `ops_bot.ops_requests` validates those parameters and builds an API request.
5. `ops_bot.clients.ops_api.OpsApiClient` calls the RCJ ops API.
6. `ops_bot.clients.signal.SignalClient` sends the response back to Signal.

## Commands

Use `uv` for all project commands:

```bash
uv sync
uv run baml-cli generate
uv run signal_bot
uv run pytest
uv run pytest tests/test_ops_bot.py
```

## Coding Rules

- Keep this project independent from `../reports`; do not import from the
  reports package.
- BAML may extract structured parameters only. Do not let BAML choose execution
  behavior, execute commands, or generate curl.
- Keep Python responsible for routing, validation, API request construction,
  API calls, and Signal replies.
- Prefer slash-command routing for deterministic behavior.
- If an endpoint requires a missing field, return a clear question instead of
  calling the API.
- Transfers are sensitive. Keep validation explicit and conservative.
- Configure logging only in entry-point `main()` functions.
- Use `logging.getLogger(__name__)` in utility modules.
- Keep generated `src/baml_client/` changes paired with BAML source changes by
  running `uv run baml-cli generate`.

## Signal

The bot supports both receive shapes exposed by `signal-cli-rest-api`:

- HTTP polling that returns `200 []` or a list of envelopes.
- WebSocket receive on `/v1/receive/{number}`.

Use `SIGNAL_BOT_RECEIVE_MODE=auto` unless debugging a specific mode.

## Testing

Tests should avoid real Signal, LLM, and RCJ ops API calls unless explicitly
marked as integration tests. Keep unit tests focused on routing and deterministic
request validation.
