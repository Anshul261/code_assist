FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project


FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    LANGGRAPH_SANDBOX_DIR=/data/lg_workspace \
    HOME=/home/app \
    TMPDIR=/tmp \
    PORT=8080

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates gosu tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --create-home --home-dir /home/app --shell /usr/sbin/nologin app \
    && mkdir -p /app /data/lg_workspace \
    && chown -R app:app /app /home/app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app langgraph_assist ./langgraph_assist
COPY --chown=app:app README.md AGENTS.md ./
COPY --chown=root:root scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN chmod 0555 /usr/local/bin/docker-entrypoint.sh \
    && find /app -type d -exec chmod 0555 {} \; \
    && find /app -type f -exec chmod 0444 {} \; \
    && chmod 0555 /app/.venv/bin/* \
    && chmod 0750 /data/lg_workspace

EXPOSE 8080

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/docker-entrypoint.sh"]
CMD ["sh", "-c", "exec uvicorn langgraph_assist.app:app --host 0.0.0.0 --port \"${PORT:-8080}\" --no-proxy-headers"]
