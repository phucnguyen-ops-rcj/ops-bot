# RCJ Ops Bot

Standalone Signal bot for RCJ ops API commands.

The bot listens to `signal-cli-rest-api`, routes a message to one of four small
BAML extraction functions, validates the typed parameters in Python, calls the
RCJ ops API, and sends the response back to Signal.

## Supported Commands

Prefer slash commands because routing is deterministic:

```text
/health
/balance kucoin USDT main
/transfer sub to main 10 USDT from kc sub account ktfsmc15
/monitor every 10 seconds
```

Keyword routing also exists for health, balance, transfer, and monitor messages.

## Setup

```bash
cd /Users/nguyentienphuc/rcj/ops_bot
cp .env.example .env
uv sync
uv run baml-cli generate
```

Set secrets outside `.env` or in your service manager:

```bash
export OPENAI_API_KEY="..."
export RCJ_OPS_BEARER_TOKEN="..."
```

Run locally:

```bash
uv run signal_bot
```

## Receive Modes

`SIGNAL_BOT_RECEIVE_MODE=auto` probes:

```text
GET <SIGNAL_BASE_URL>/v1/receive/<SIGNAL_SENDER>
```

If the local Signal API returns HTTP `200 []`, the bot uses polling every
`SIGNAL_BOT_POLL_SECONDS`. Otherwise it uses the WebSocket form of the same
endpoint.

## Project Layout

```text
baml_src/                 BAML client and extraction schemas
src/baml_client/          Generated BAML Python client
src/ops_bot/clients/      Signal and RCJ ops API clients
src/ops_bot/scripts/      Long-running Signal listener entrypoint
tests/                    Deterministic routing/request tests
```

## Safety Boundaries

BAML only extracts typed parameters. Python owns route selection, validation,
request construction, API calls, and Signal replies. The model never executes
shell commands or constructs arbitrary curl.
