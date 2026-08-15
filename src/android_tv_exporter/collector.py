"""Background per-device collector.

Each device gets one `DeviceCollector` running in its own thread. The loop reads
stable /proc and /sys sources, parses them, and updates Prometheus metrics.
Failures are counted and logged; the loop keeps running so one flaky device
never takes down the exporter.
"""

from __future__ import annotations

import logging
import threading
import time

from . import metrics, parsers
from .device import Device

logger = logging.getLogger(__name__)

# Sysfs globs are expanded on-device with shell; we read them in bulk where we
# can to minimise the number of (slow) adb round-trips.
_MEMINFO_FIELDS = {
    "MemTotal": "total",
    "MemAvailable": "available",
    "MemFree": "free",
    "Buffers": "buffers",
    "Cached": "cached",
}


class DeviceCollector:
    def __init__(self, device: Device, interval: int):
        self.device = device
        self.interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name=f"collector-{device.serial}", daemon=True
        )
        # Previous samples for delta-based metrics.
        self._prev_cpu: dict[str, tuple[int, int]] = {}
        self._prev_net: dict[str, dict[str, int]] = {}

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        serial = self.device.serial
        while not self._stop.is_set():
            start = time.monotonic()
            try:
                self.device.connect()
                self._collect()
                metrics.up.labels(serial).set(1)
                metrics.collect_duration.labels(serial).set(time.monotonic() - start)
            except Exception as exc:  # noqa: BLE001 - keep the loop alive
                metrics.up.labels(serial).set(0)
                metrics.collect_errors.labels(serial).inc()
                logger.warning("collection failed for %s: %s", serial, exc)
            self._stop.wait(self.interval)

    def _collect(self) -> None:
        serial = self.device.serial

        # Identity (cached after first fetch).
        labels = self.device.labels()
        metrics.device_info.labels(
            labels["device"],
            labels["android_version"],
            labels["model"],
            labels["manufacturer"],
            labels["name"],
            labels["board"],
        ).set(1)

        self._collect_cpu(serial)
        self._collect_cpu_freq(serial)
        self._collect_memory(serial)
        self._collect_disk(serial)
        self._collect_thermal(serial)
        self._collect_network(serial)
        self._collect_system(serial)
        self._collect_gpu(serial)
        self._collect_power(serial)

    def _collect_cpu(self, serial: str) -> None:
        stat = parsers.parse_proc_stat(self.device.cat("/proc/stat"))
        for name, sample in stat.items():
            prev = self._prev_cpu.get(name)
            if prev is not None:
                metrics.cpu_usage.labels(serial, name).set(parsers.cpu_percent(prev, sample))
        self._prev_cpu = stat

    def _collect_cpu_freq(self, serial: str) -> None:
        # Read every core's current frequency in one shot.
        raw = self.device.shell(
            "for f in /sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq; do "
            'echo "$f $(cat $f 2>/dev/null)"; done'
        )
        for line in raw.splitlines():
            path, _, value = line.partition(" ")
            khz = parsers.parse_hz(value)
            if khz is None:
                continue
            core = path.split("/")[5]  # .../cpu/cpuN/cpufreq/...
            metrics.cpu_freq.labels(serial, core).set(khz * 1000)  # kHz -> Hz

    def _collect_memory(self, serial: str) -> None:
        info = parsers.parse_meminfo(self.device.cat("/proc/meminfo"))
        for key, field in _MEMINFO_FIELDS.items():
            if key in info:
                metrics.memory.labels(serial, field).set(info[key])

    def _collect_disk(self, serial: str) -> None:
        for mount in parsers.parse_df(self.device.shell("df -kP")):
            name = mount["mount"]
            metrics.disk.labels(serial, name, "size").set(mount["size"])
            metrics.disk.labels(serial, name, "used").set(mount["used"])
            metrics.disk.labels(serial, name, "available").set(mount["available"])

    def _collect_thermal(self, serial: str) -> None:
        # /sys/class/thermal needs root on many boxes; dumpsys thermalservice
        # exposes named HAL temperatures unprivileged in a stable format.
        raw = self.device.shell("dumpsys thermalservice")
        for zone, celsius in parsers.parse_thermal_dumpsys(raw).items():
            metrics.temperature.labels(serial, zone).set(celsius)

    def _collect_network(self, serial: str) -> None:
        current = parsers.parse_net_dev(self.device.cat("/proc/net/dev"))
        for iface, counters in current.items():
            prev = self._prev_net.get(iface)
            if prev is not None:
                self._inc_counter(metrics.network_rx, serial, iface, prev, counters, "rx_bytes")
                self._inc_counter(metrics.network_tx, serial, iface, prev, counters, "tx_bytes")
        self._prev_net = current

    @staticmethod
    def _inc_counter(metric, serial, iface, prev, curr, key) -> None:
        delta = curr[key] - prev[key]
        if delta < 0:  # device rebooted / counter reset
            delta = curr[key]
        metric.labels(serial, iface).inc(delta)

    def _collect_system(self, serial: str) -> None:
        metrics.uptime.labels(serial).set(parsers.parse_uptime(self.device.cat("/proc/uptime")))

        load = parsers.parse_loadavg(self.device.cat("/proc/loadavg"))
        if load:
            metrics.load.labels(serial, "1").set(load["load1"])
            metrics.load.labels(serial, "5").set(load["load5"])
            metrics.load.labels(serial, "15").set(load["load15"])
            if "procs_running" in load:
                metrics.processes.labels(serial, "running").set(load["procs_running"])
            if "procs_total" in load:
                metrics.processes.labels(serial, "total").set(load["procs_total"])

    def _collect_gpu(self, serial: str) -> None:
        # GPU frequency/utilisation need root on most boxes; the total GPU
        # memory from `dumpsys gpu` is available unprivileged. Best-effort.
        total = parsers.parse_gpu_meminfo(self.device.shell("dumpsys gpu"))
        if total is not None:
            metrics.gpu_memory.labels(serial).set(total)

    def _collect_power(self, serial: str) -> None:
        # Only the AC/USB online state from the battery service is trustworthy
        # on a mains box. voltage/temperature/charge are hardcoded placeholders
        # (present: false), so they are intentionally not exported.
        battery = parsers.parse_battery(self.device.shell("dumpsys battery"))
        if "ac_online" in battery:
            metrics.power_online.labels(serial, "ac").set(battery["ac_online"])
        if "usb_online" in battery:
            metrics.power_online.labels(serial, "usb").set(battery["usb_online"])
