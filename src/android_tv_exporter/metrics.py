"""Prometheus metric definitions.

Identifying labels (android version, model, ...) live on a single
`androidtv_device_info` gauge. Functional metrics carry only `device` plus any
dimension of their own (cpu, mount, interface, zone), which keeps cardinality low.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge

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
network_rx = Counter(
    "androidtv_network_receive_bytes_total",
    "Bytes received per interface.",
    ["device", "interface"],
)
network_tx = Counter(
    "androidtv_network_transmit_bytes_total",
    "Bytes transmitted per interface.",
    ["device", "interface"],
)

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
