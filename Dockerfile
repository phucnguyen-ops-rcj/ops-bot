FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    HOME="/home/opsbot" \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates openssh-client \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY README.md ./
COPY baml_src ./baml_src
COPY src ./src

RUN uv sync --locked --no-dev

RUN groupadd --system opsbot \
    && useradd --system --gid opsbot --home-dir /home/opsbot --shell /usr/sbin/nologin opsbot \
    && mkdir -p /home/opsbot \
    && chown -R opsbot:opsbot /app /home/opsbot

USER opsbot

CMD ["signal_bot"]
