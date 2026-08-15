"""Typer CLI: parse options, start the HTTP server, launch collectors."""

from __future__ import annotations

import logging
import signal
import threading

import adbutils
import typer
from prometheus_client import start_http_server

from . import __url__, __version__
from .collector import DeviceCollector
from .config import resolve_settings
from .device import Device

app = typer.Typer(add_completion=False, help="Prometheus exporter for Android TV over ADB.")

logger = logging.getLogger("android_tv_exporter")

BANNER_ART = r"""
     _              _           _     _ _______     __
    / \   _ __   __| |_ __ ___ (_) __| |_   _\ \   / /
   / _ \ | '_ \ / _` | '__/ _ \| |/ _` | | |  \ \ / / 
  / ___ \| | | | (_| | | | (_) | | (_| | | |   \ V /  
 /_/___\_\_| |_|\__,_|_|  \___/|_|\__,_| |_|    \_/   
      | ____|_  ___ __   ___  _ __| |_ ___ _ __            
      |  _| \ \/ / '_ \ / _ \| '__| __/ _ \ '__|           
      | |___ >  <| |_) | (_) | |  | ||  __/ |              
      |_____/_/\_\ .__/ \___/|_|   \__\___|_|              
                  |_|                                       
"""


def _banner() -> str:
    """ASCII header with the version and repository URL from package metadata."""
    version = f"Version: {__version__}\n"
    url = f"Project: {__url__}\n"
    footer = version + url
    return f"{BANNER_ART}{footer}\n"


@app.command()
def main(
    adb_host: str = typer.Option(None, help="ADB server host. [env: ANDROIDTV_ADB_HOST]"),
    adb_port: int = typer.Option(None, help="ADB server port. [env: ANDROIDTV_ADB_PORT]"),
    device: list[str] = typer.Option(
        None, "--device", help="Device serial, repeatable. [env: ANDROIDTV_DEVICES]"
    ),
    listen_host: str = typer.Option(None, help="Exporter bind host. [env: ANDROIDTV_LISTEN_HOST]"),
    listen_port: int = typer.Option(None, help="Exporter bind port. [env: ANDROIDTV_LISTEN_PORT]"),
    interval: int = typer.Option(None, help="Poll interval seconds. [env: ANDROIDTV_INTERVAL]"),
    timeout: int = typer.Option(None, help="Per-device ADB timeout. [env: ANDROIDTV_TIMEOUT]"),
    log_level: str = typer.Option(None, help="Log level. [env: ANDROIDTV_LOG_LEVEL]"),
) -> None:
    settings = resolve_settings(
        adb_host=adb_host,
        adb_port=adb_port,
        devices=device,
        listen_host=listen_host,
        listen_port=listen_port,
        interval=interval,
        timeout=timeout,
        log_level=log_level,
    )

    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    print(_banner(), flush=True)

    if not settings.devices:
        raise typer.BadParameter("No devices configured. Pass --device or set ANDROIDTV_DEVICES.")

    client = adbutils.AdbClient(host=settings.adb_host, port=settings.adb_port)

    collectors = [
        DeviceCollector(Device(client, serial, timeout=settings.timeout), settings.interval)
        for serial in settings.devices
    ]

    start_http_server(settings.listen_port, addr=settings.listen_host)
    logger.info(
        "exporter listening on %s:%s/metrics for %d device(s)",
        settings.listen_host,
        settings.listen_port,
        len(collectors),
    )

    for collector in collectors:
        collector.start()

    logger.info(
        "if you see 'collection failed' / connection errors below on first boot, "
        "this is expected: the container's ADB key is not yet authorized on the "
        "TV. Run 'docker compose exec android-tv-exporter adb disconnect <ip:port>' "
        "then 'adb connect <ip:port>', accept the prompt on the TV, and restart the "
        "container. See the README 'First-time device setup' section."
    )

    # Block until we're asked to stop. SIGTERM (docker stop) and SIGINT (Ctrl-C)
    # both release the event so shutdown is prompt instead of waiting for SIGKILL.
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    stop.wait()

    logger.info("shutting down")
    for collector in collectors:
        collector.stop()


if __name__ == "__main__":
    app()
