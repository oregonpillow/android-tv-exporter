# Multi-stage build using uv for fast, reproducible dependency installation.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder


ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install dependencies first (cached layer), then the project itself.
COPY pyproject.toml uv.lock* README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable 2>/dev/null \
    || uv sync --no-dev --no-editable


FROM python:3.12-slim-bookworm AS runtime

# adb is required: the exporter talks to a local ADB server which bridges to
# the Android TV devices over TCP/IP.
RUN apt-get update \
    && apt-get install -y --no-install-recommends android-tools-adb \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for the app.
RUN useradd --create-home --uid 10001 exporter

COPY --from=builder /app/.venv /app/.venv
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH" \
    HOME=/home/exporter \
    ANDROIDTV_LISTEN_HOST=0.0.0.0 \
    ANDROIDTV_LISTEN_PORT=9100

# Make the home dir writable by any UID (compose may override the user at
# runtime via `user:`), so adb can always create ~/.android/adbkey.
RUN chmod -R g+rwX /home/exporter && chgrp -R 0 /home/exporter

USER exporter
WORKDIR /home/exporter

EXPOSE 9100

ENTRYPOINT ["docker-entrypoint.sh"]
