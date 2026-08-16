"""Tests for the gappy-series behavior in DeviceCollector.

When a device is unreachable, its data series should be removed so graphs show
a gap rather than a stale last-known value. `up` still reports 0 separately.
"""

from __future__ import annotations

from types import SimpleNamespace

from android_tv_exporter import metrics
from android_tv_exporter.collector import DeviceCollector

SERIAL = "10.0.0.5:5555"


def _make_collector() -> DeviceCollector:
    return DeviceCollector(SimpleNamespace(serial=SERIAL), interval=15)


def _has_series(metric, labels: tuple[str, ...]) -> bool:
    return labels in metric._metrics


def test_set_records_and_exports_series() -> None:
    c = _make_collector()
    c._pending = set()
    c._set(metrics.cpu_usage, (SERIAL, "cpu"), 42.0)
    c._active = c._pending

    assert _has_series(metrics.cpu_usage, (SERIAL, "cpu"))
    assert metrics.cpu_usage.labels(SERIAL, "cpu")._value.get() == 42.0


def test_failure_drops_all_device_series() -> None:
    c = _make_collector()
    c._pending = set()
    c._set(metrics.cpu_usage, (SERIAL, "cpu"), 10.0)
    c._set(metrics.memory, (SERIAL, "total"), 2048.0)
    c._active = c._pending

    # Simulate the failure path in _run.
    c._drop_series(c._active)
    c._active = set()

    assert not _has_series(metrics.cpu_usage, (SERIAL, "cpu"))
    assert not _has_series(metrics.memory, (SERIAL, "total"))


def test_vanished_dimension_is_removed_between_cycles() -> None:
    c = _make_collector()

    # Cycle 1: two interfaces present.
    c._pending = set()
    c._set(metrics.temperature, (SERIAL, "cpu"), 40.0)
    c._set(metrics.temperature, (SERIAL, "gpu"), 45.0)
    c._active = c._pending

    # Cycle 2: the gpu zone disappears.
    c._pending = set()
    c._set(metrics.temperature, (SERIAL, "cpu"), 41.0)
    c._drop_series(c._active - c._pending)
    c._active = c._pending

    assert _has_series(metrics.temperature, (SERIAL, "cpu"))
    assert not _has_series(metrics.temperature, (SERIAL, "gpu"))


def _net_value(device: str, iface: str, kind: str) -> float | None:
    """Return the raw rx/tx counter value emitted by the network collector."""
    for metric in metrics.network.collect():
        for sample in metric.samples:
            if sample.labels == {"device": device, "interface": iface} and sample.name.endswith(
                kind
            ):
                return sample.value
    return None


def test_network_exposes_raw_totals() -> None:
    metrics.network.set(SERIAL, "eth0", 1000, 2000)
    assert _net_value(SERIAL, "eth0", "receive_bytes_total") == 1000
    assert _net_value(SERIAL, "eth0", "transmit_bytes_total") == 2000
    metrics.network.remove_device(SERIAL)


def test_network_removed_on_device_failure() -> None:
    metrics.network.set(SERIAL, "eth0", 1000, 2000)
    metrics.network.remove_device(SERIAL)
    assert _net_value(SERIAL, "eth0", "receive_bytes_total") is None


def test_network_resumes_monotonic_after_gap() -> None:
    # Before outage the device reported 1000 bytes; it's then removed (gap).
    metrics.network.set(SERIAL, "eth0", 1000, 2000)
    metrics.network.remove_device(SERIAL)
    # On reconnect the device's raw total has grown; we emit it directly, so the
    # counter continues upward across the gap rather than resetting to a delta.
    metrics.network.set(SERIAL, "eth0", 1500, 2500)
    assert _net_value(SERIAL, "eth0", "receive_bytes_total") == 1500
    metrics.network.remove_device(SERIAL)
