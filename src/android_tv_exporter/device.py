"""Thin wrapper around an adbutils device.

Keeps ADB details in one place: connecting via the local ADB server, running
shell commands / reading files with a timeout, caching the low-cardinality
`getprop` labels, and reporting reachability.
"""

from __future__ import annotations

import logging

import adbutils

logger = logging.getLogger(__name__)

# getprop keys -> Prometheus label names. Fetched once and cached.
_LABEL_PROPS = {
    "android_version": "ro.build.version.release",
    "model": "ro.product.model",
    "manufacturer": "ro.product.manufacturer",
    "name": "ro.product.name",
    "board": "ro.product.board",
}


class Device:
    """A single Android TV device reachable over the ADB server."""

    def __init__(self, client: adbutils.AdbClient, serial: str, timeout: float = 10.0):
        self._client = client
        self.serial = serial
        self.timeout = timeout
        self._labels: dict[str, str] | None = None

    def connect(self) -> None:
        """Ask the ADB server to (re)connect to the device over TCP/IP.

        Serials without a port (USB serials) are left to the server as-is.
        """
        if ":" in self.serial:
            self._client.connect(self.serial, timeout=self.timeout)

    def _device(self) -> adbutils.AdbDevice:
        return self._client.device(serial=self.serial)

    def shell(self, command: str) -> str:
        """Run a shell command and return its stripped stdout."""
        result = self._device().shell(command, timeout=self.timeout)
        return result if isinstance(result, str) else result.decode("utf-8", "replace")

    def cat(self, path: str) -> str:
        """Read a file on the device via `cat`."""
        return self.shell(f"cat {path}")

    def labels(self) -> dict[str, str]:
        """Return cached identifying labels, fetching them once.

        Always includes `device` (the serial). Missing props become "unknown".
        """
        if self._labels is None:
            dev = self._device()
            resolved = {"device": self.serial}
            for label, prop in _LABEL_PROPS.items():
                try:
                    resolved[label] = dev.getprop(prop) or "unknown"
                except adbutils.AdbError:
                    resolved[label] = "unknown"
            self._labels = resolved
        return self._labels

    def label_names(self) -> list[str]:
        return ["device", *_LABEL_PROPS.keys()]
