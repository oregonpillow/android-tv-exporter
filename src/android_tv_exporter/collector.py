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

"""Sysfs globs are expanded on-device with shell; we read them in bulk where we
can to minimise the number of (slow) adb round-trips."""
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
        """Label series currently exported for this device, so we can remove them
        when the device goes away (gappy series) or when a dimension vanishes."""
        self._active: set[tuple[object, tuple[str, ...]]] = set()
        self._pending: set[tuple[object, tuple[str, ...]]] = set()
        """Network interfaces exported this device (tracked separately because
        the raw byte counters live in a custom collector, not a Gauge/Counter)."""
        self._active_net: set[str] = set()
        self._pending_net: set[str] = set()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _set(self, metric, labels: tuple[str, ...], value: float) -> None:
        """Set a gauge series and record it as active for this cycle."""
        metric.labels(*labels).set(value)
        self._pending.add((metric, labels))

    def _drop_series(self, series: set[tuple[object, tuple[str, ...]]]) -> None:
        for metric, labels in series:
            try:
                metric.remove(*labels)
            except KeyError:
                pass  # already gone

    def _run(self) -> None:
        serial = self.device.serial
        while not self._stop.is_set():
            start = time.monotonic()
            self._pending = set()
            self._pending_net = set()
            try:
                self.device.connect()
                self._collect()
                """Remove series that were present last cycle but not this one
                (e.g. a network interface or thermal zone disappeared)."""
                self._drop_series(self._active - self._pending)
                self._active = self._pending
                for iface in self._active_net - self._pending_net:
                    metrics.network.remove(serial, iface)
                self._active_net = self._pending_net
                metrics.up.labels(serial).set(1)
                metrics.collect_duration.labels(serial).set(time.monotonic() - start)
            except Exception as exc:  # noqa: BLE001 - keep the loop alive
                """Device unreachable: drop all of its data series so graphs show
                a gap instead of a stale flat line. up/collect_errors remain.
                Network counters are dropped too; on reconnect they resume from
                the device's real raw total, staying monotonic across the gap."""
                self._drop_series(self._active)
                self._active = set()
                metrics.network.remove_device(serial)
                self._active_net = set()
                metrics.up.labels(serial).set(0)
                metrics.collect_errors.labels(serial).inc()
                logger.warning("collection failed for %s: %s", serial, exc)
            self._stop.wait(self.interval)

    def _collect(self) -> None:
        serial = self.device.serial

        # Identity (cached after first fetch).
        labels = self.device.labels()
        self._set(
            metrics.device_info,
            (
                labels["device"],
                labels["android_version"],
                labels["model"],
                labels["manufacturer"],
                labels["name"],
                labels["board"],
            ),
            1,
        )

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
                self._set(metrics.cpu_usage, (serial, name), parsers.cpu_percent(prev, sample))
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
            self._set(metrics.cpu_freq, (serial, core), khz * 1000)  # kHz -> Hz

    def _collect_memory(self, serial: str) -> None:
        info = parsers.parse_meminfo(self.device.cat("/proc/meminfo"))
        for key, field in _MEMINFO_FIELDS.items():
            if key in info:
                self._set(metrics.memory, (serial, field), info[key])

    def _collect_disk(self, serial: str) -> None:
        for mount in parsers.parse_df(self.device.shell("df -kP")):
            name = mount["mount"]
            self._set(metrics.disk, (serial, name, "size"), mount["size"])
            self._set(metrics.disk, (serial, name, "used"), mount["used"])
            self._set(metrics.disk, (serial, name, "available"), mount["available"])

    def _collect_thermal(self, serial: str) -> None:
        """Collect thermal-zone temperatures.

        /sys/class/thermal needs root on many boxes; dumpsys thermalservice
        exposes named HAL temperatures unprivileged in a stable format.
        """
        raw = self.device.shell("dumpsys thermalservice")
        for zone, celsius in parsers.parse_thermal_dumpsys(raw).items():
            self._set(metrics.temperature, (serial, zone), celsius)

    def _collect_network(self, serial: str) -> None:
        """Collect per-interface network byte totals.

        Expose the device's own raw cumulative byte totals directly. No delta
        math: monotonic within the device's uptime, and Prometheus handles
        genuine resets (device reboots) at query time.
        """
        current = parsers.parse_net_dev(self.device.cat("/proc/net/dev"))
        for iface, counters in current.items():
            metrics.network.set(serial, iface, counters["rx_bytes"], counters["tx_bytes"])
            self._pending_net.add(iface)

    def _collect_system(self, serial: str) -> None:
        self._set(metrics.uptime, (serial,), parsers.parse_uptime(self.device.cat("/proc/uptime")))

        load = parsers.parse_loadavg(self.device.cat("/proc/loadavg"))
        if load:
            self._set(metrics.load, (serial, "1"), load["load1"])
            self._set(metrics.load, (serial, "5"), load["load5"])
            self._set(metrics.load, (serial, "15"), load["load15"])
            if "procs_running" in load:
                self._set(metrics.processes, (serial, "running"), load["procs_running"])
            if "procs_total" in load:
                self._set(metrics.processes, (serial, "total"), load["procs_total"])

    def _collect_gpu(self, serial: str) -> None:
        """Collect total GPU memory in use (best-effort).

        GPU frequency/utilisation need root on most boxes; the total GPU
        memory from `dumpsys gpu` is available unprivileged.
        """
        total = parsers.parse_gpu_meminfo(self.device.shell("dumpsys gpu"))
        if total is not None:
            self._set(metrics.gpu_memory, (serial,), total)

    def _collect_power(self, serial: str) -> None:
        """Collect AC/USB power-source online state.

        Only the AC/USB online state from the battery service is trustworthy
        on a mains box. voltage/temperature/charge are hardcoded placeholders
        (present: false), so they are intentionally not exported.
        """
        battery = parsers.parse_battery(self.device.shell("dumpsys battery"))
        if "ac_online" in battery:
            self._set(metrics.power_online, (serial, "ac"), battery["ac_online"])
        if "usb_online" in battery:
            self._set(metrics.power_online, (serial, "usb"), battery["usb_online"])
