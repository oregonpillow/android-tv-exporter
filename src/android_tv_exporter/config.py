"""Runtime settings for the exporter.

Values come from CLI flags with environment-variable fallbacks. The CLI layer
(`cli.py`) is responsible for the precedence: it passes an explicit value when a
flag is set, otherwise `None`, and the resolver here falls back to the matching
environment variable and finally the default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    adb_host: str = "127.0.0.1"
    adb_port: int = 5037
    devices: list[str] = field(default_factory=list)
    listen_host: str = "0.0.0.0"
    listen_port: int = 9100
    interval: int = 15
    timeout: int = 10
    log_level: str = "INFO"


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value else default


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if not value:
        return default
    return int(value)


def _parse_devices(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def resolve_settings(
    adb_host: str | None = None,
    adb_port: int | None = None,
    devices: list[str] | None = None,
    listen_host: str | None = None,
    listen_port: int | None = None,
    interval: int | None = None,
    timeout: int | None = None,
    log_level: str | None = None,
) -> Settings:
    """Build Settings from CLI values, falling back to env vars then defaults.

    A non-None argument (a CLI flag that was set) always wins over the
    environment variable.
    """
    resolved_devices = (
        devices if devices else _parse_devices(os.environ.get("ANDROIDTV_DEVICES", ""))
    )

    return Settings(
        adb_host=adb_host or _env_str("ANDROIDTV_ADB_HOST", "127.0.0.1"),
        adb_port=adb_port if adb_port is not None else _env_int("ANDROIDTV_ADB_PORT", 5037),
        devices=resolved_devices,
        listen_host=listen_host or _env_str("ANDROIDTV_LISTEN_HOST", "0.0.0.0"),
        listen_port=listen_port
        if listen_port is not None
        else _env_int("ANDROIDTV_LISTEN_PORT", 9100),
        interval=interval if interval is not None else _env_int("ANDROIDTV_INTERVAL", 15),
        timeout=timeout if timeout is not None else _env_int("ANDROIDTV_TIMEOUT", 10),
        log_level=log_level or _env_str("ANDROIDTV_LOG_LEVEL", "INFO"),
    )
