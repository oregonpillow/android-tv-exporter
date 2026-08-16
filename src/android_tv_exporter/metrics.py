"""Prometheus metric definitions.

Identifying labels (android version, model, ...) live on a single
`androidtv_device_info` gauge. Functional metrics carry only `device` plus any
dimension of their own (cpu, mount, interface, zone), which keeps cardinality low.
"""

from __future__ import annotations

import threading

from prometheus_client import REGISTRY, Counter, Gauge
from prometheus_client.core import CounterMetricFamily

# Identity ------------------------------------------------------------------
device_info = Gauge(
    "androidtv_device_info",
    "Static device identity; value is always 1.",
    ["device", "android_version", "model", "manufacturer", "name", "board"],
)

up = Gauge("androidtv_up", "1 if the device was reachable at the last scrape.", ["device"])

# CPU -----------------------------------------------------------------------
cpu_usage = Gauge(
    "androidtv_cpu_usage_percent",
    "CPU busy percentage. cpu='cpu' is the aggregate; cpu='cpuN' per core.",
    ["device", "cpu"],
)
cpu_freq = Gauge(
    "androidtv_cpu_frequency_hertz",
    "Current CPU clock frequency per core.",
    ["device", "cpu"],
)

# Memory --------------------------------------------------------------------
memory = Gauge(
    "androidtv_memory_bytes",
    "Memory statistics from /proc/meminfo. field='total'|'available'|...",
    ["device", "field"],
)

# Disk ----------------------------------------------------------------------
disk = Gauge(
    "androidtv_disk_bytes",
    "Filesystem usage. field='size'|'used'|'available'.",
    ["device", "mount", "field"],
)

# Thermal -------------------------------------------------------------------
temperature = Gauge(
    "androidtv_temperature_celsius",
    "Thermal zone temperature.",
    ["device", "zone"],
)

# GPU (best-effort) ---------------------------------------------------------
gpu_memory = Gauge(
    "androidtv_gpu_memory_bytes",
    "Total GPU memory in use, from `dumpsys gpu`.",
    ["device"],
)

# Power (best-effort) -------------------------------------------------------
power_online = Gauge(
    "androidtv_power_online",
    "Power source online state. source='ac'|'usb'; value 1/0.",
    ["device", "source"],
)

# Network -------------------------------------------------------------------
"""Exposed as the device's own raw cumulative byte counters (like node_exporter),
not a self-accumulated delta. A custom collector emits the last cached value
for each interface, so the exported counter stays monotonic within the
device's uptime and Prometheus handles genuine resets (device reboots) itself."""


class _NetworkCollector:
    """Holds the latest raw rx/tx byte totals per (device, interface)."""

    def __init__(self) -> None:
        self._values: dict[tuple[str, str], tuple[int, int]] = {}
        self._lock = threading.Lock()

    def set(self, device: str, iface: str, rx: int, tx: int) -> None:
        with self._lock:
            self._values[(device, iface)] = (rx, tx)

    def remove(self, device: str, iface: str) -> None:
        with self._lock:
            self._values.pop((device, iface), None)

    def remove_device(self, device: str) -> None:
        with self._lock:
            self._values = {k: v for k, v in self._values.items() if k[0] != device}

    def collect(self):
        rx = CounterMetricFamily(
            "androidtv_network_receive_bytes",
            "Bytes received per interface (device's raw cumulative counter).",
            labels=["device", "interface"],
        )
        tx = CounterMetricFamily(
            "androidtv_network_transmit_bytes",
            "Bytes transmitted per interface (device's raw cumulative counter).",
            labels=["device", "interface"],
        )
        with self._lock:
            items = list(self._values.items())
        for (device, iface), (rx_bytes, tx_bytes) in items:
            rx.add_metric([device, iface], rx_bytes)
            tx.add_metric([device, iface], tx_bytes)
        yield rx
        yield tx


network = _NetworkCollector()
REGISTRY.register(network)


# System --------------------------------------------------------------------
uptime = Gauge("androidtv_uptime_seconds", "Device uptime in seconds.", ["device"])
load = Gauge(
    "androidtv_load_average",
    "System load average. period='1'|'5'|'15'.",
    ["device", "period"],
)
processes = Gauge(
    "androidtv_processes",
    "Process counts. state='running'|'total'.",
    ["device", "state"],
)

# Collector meta ------------------------------------------------------------
collect_duration = Gauge(
    "androidtv_collect_duration_seconds",
    "Duration of the last successful metric collection.",
    ["device"],
)
collect_errors = Counter(
    "androidtv_collect_errors_total",
    "Number of failed collection cycles.",
    ["device"],
)
