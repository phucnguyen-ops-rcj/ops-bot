# RCJ Ops Bot

Standalone Signal bot for RCJ ops API commands.

The bot listens to `signal-cli-rest-api`, routes a message to one of six small
BAML extraction functions, validates the typed parameters in Python, calls the
RCJ ops API, and sends the response back to Signal.

## Supported Commands

Prefer slash commands because routing is deterministic:

```text
/health
/balance kucoin USDT main
/transfer sub to main 10 USDT from kc sub account ktfsmc15
/monitor every 10 seconds
/volume-fills KAIO
/stacker-status KAIO-USDT
/help
/new-listing
/new-listing-dryrun
/schedule-volume
/schedule-mirror
/schedule-stacker
/schedule-new-listing
/remove-schedules
symbol: ATWO
market: spot
tier: C
create_new_gate_way: false
price decimals: 5
quantity decimals: 1
feed port: 41739
gateway port: 45704
```

Keyword routing also exists for health, balance, transfer, monitor,
`volume-fills`, and `stacker-status` messages.

`/volume-fills` posts to `/get_volume_strategy_fills` using
`base_currency`/`quote_currency` derived from the symbol. `/stacker-status`
posts to `/get_stacker_accepted_orders` using the normalized symbol. Both
accept an optional `date` in `YYYYMMDD` format.

`/new-listing` prepares the generated config under `.docker-data/new_listing/config`
locally or `/data/new_listing/config` in Docker, updates the matching
`gateway_symbols.yml` and `trading_volume.json` in the same shared data root,
then runs the workflow in real mode.
`/new-listing-dryrun` does the same setup work but runs the workflow in dry-run
mode for verification. After either command, the bot sends the generated config
file and run log file back to Signal as attachments. `/help` lists all supported bot commands. Run the
generated config manually with:

```bash
uv run new_listing ATWO --dry-run
uv run new_listing ATWO --execution-mode ssh
uv run new_listing ATWO --execution-mode local
```

`/schedule-volume`, `/schedule-mirror`, `/schedule-stacker`, and
`/schedule-new-listing` do not use BAML extraction. They expect a JSON payload
and send the Prefect scheduling result back through Signal. Use
`scheduled_time` in a simple local format like `"05:00"` or
`"2026-05-22 09:30"`, or full ISO 8601 if needed.

`/schedule-volume` and `/schedule-mirror` create one Prefect deployment run.
`/schedule-stacker` creates four one-time runs for levels 1, 2, 3, and 4 using
`stacker_interval_minutes`, which defaults to `10`. `/schedule-new-listing`
creates stackers 1 to 4 from the requested start time, volume at `+65`
minutes, and mirror at `+120` minutes by default.

`/remove-schedules` deletes Prefect runs by explicit `flow_run_id` or
`flow_run_ids`. Use the run IDs returned by the schedule commands in Signal.

## Setup

```bash
cd /Users/nguyentienphuc/rcj/ops_bot
cp .env.example .env
uv sync
uv run baml-cli generate
```

Set secrets in `.env` for local/Docker runs, or in your service manager:

```env
OPENAI_API_KEY=sk-...
RCJ_OPS_BEARER_TOKEN=...
```

When using `.env` with `docker run --env-file`, prefer unquoted values:

```env
SIGNAL_SENDER=+84559854979
SIGNAL_BASE_URL=http://127.0.0.1:8081
```

Run locally:

```bash
uv run signal_bot
```

## Docker

Build the service image:

```bash
docker build -t rcj-ops-bot:latest .
```

Run it against a `signal-cli-rest-api` instance on the host:

```bash
mkdir -p .docker-data

docker run -d --name rcj-ops-bot \
  --env-file .env \
  -e SIGNAL_BASE_URL=http://host.docker.internal:8081 \
  -e SIGNAL_GROUP_CACHE_PATH=/data/signal_groups.yml \
  -v "$HOME/.ssh:/home/opsbot/.ssh:ro" \
  -v "$(pwd)/.docker-data:/data" \
  --restart unless-stopped \
  rcj-ops-bot:latest
```

Useful commands:

```bash
docker logs -f rcj-ops-bot
docker stop rcj-ops-bot
docker rm rcj-ops-bot
docker restart rcj-ops-bot
```

To deploy new logic after code changes, rebuild the image with the same tag and
replace the running container. You do not need to manually remove the old
image.

```bash
docker rm -f rcj-ops-bot || true

docker build -t rcj-ops-bot:latest .

docker run -d --name rcj-ops-bot \
  --env-file .env \
  -e SIGNAL_BASE_URL=http://host.docker.internal:8081 \
  -e SIGNAL_GROUP_CACHE_PATH=/data/signal_groups.yml \
  -v "$HOME/.ssh:/home/opsbot/.ssh:ro" \
  -v "$(pwd)/.docker-data:/data" \
  --restart unless-stopped \
  rcj-ops-bot:latest
```

One-line version:

```bash
docker rm -f rcj-ops-bot || true && \
docker build -t rcj-ops-bot:latest . && \
docker run -d --name rcj-ops-bot \
  --env-file .env \
  -e SIGNAL_BASE_URL=http://host.docker.internal:8081 \
  -e SIGNAL_GROUP_CACHE_PATH=/data/signal_groups.yml \
  -v "$HOME/.ssh:/home/opsbot/.ssh:ro" \
  -v "$(pwd)/.docker-data:/data" \
  --restart unless-stopped \
  rcj-ops-bot:latest
```

If you want to reclaim old unused image layers later:

```bash
docker image prune -f
```

`SIGNAL_BASE_URL` uses `host.docker.internal` so the container can reach the
Signal REST API running on the host. The SSH mount is needed when
`RCJ_OPS_EXECUTION_MODE=ssh`. The `/data` mount persists the group-id cache
between container runs. New-listing generated config, logs, gateway symbols,
and trading-volume state also live under that same `/data/new_listing` tree.

## Receive Modes

`SIGNAL_BOT_RECEIVE_MODE=auto` probes:

```text
GET <SIGNAL_BASE_URL>/v1/receive/<SIGNAL_SENDER>
```

If the local Signal API returns HTTP `200 []`, the bot uses polling every
`SIGNAL_BOT_POLL_SECONDS`. Otherwise it uses the WebSocket form of the same
endpoint.

## Group Chats

In group chats, the bot ignores messages unless it is mentioned. Configure one
or more comma-separated text aliases:

```bash
SIGNAL_BOT_MENTION_ALIASES="opsbot,@opsbot"
```

For replies to work in a group, the bot maps receive-side group ids to the
sendable `group.xxx` id from the Signal API group list:

```bash
curl http://127.0.0.1:8081/v1/groups/+1234567890
SIGNAL_GROUP_CACHE_PATH="signal_groups.yml"
# Optional manual fallback:
SIGNAL_GROUP_ID="group.xxx"
```

On the first group reply, the bot calls `/v1/groups/{number}` if the receive
payload's internal group id is not already in the cache file. It writes the
mapping to `SIGNAL_GROUP_CACHE_PATH` for later runs.

Then use the bot in the group like:

```text
@opsbot /balance kucoin USDT main
@opsbot withdraw 10 USDT from kc to binance
```

One-to-one messages are still handled without a mention.

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
