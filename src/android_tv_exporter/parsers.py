"""Pure parsers for stable Android /proc, /sys and `df` sources.

Every function takes raw command/file text and returns plain Python values.
They import nothing from adb or prometheus so they are trivially unit-testable.
Parsers tolerate unexpected lines by skipping them rather than raising.
"""

from __future__ import annotations

import re


def parse_proc_stat(text: str) -> dict[str, tuple[int, int]]:
    """Parse /proc/stat CPU lines into {cpu_name: (busy, total)} jiffies.

    Returns an entry for aggregate "cpu" and each "cpuN". CPU percentages are
    computed by the caller from the delta between two reads.
    """
    result: dict[str, tuple[int, int]] = {}
    for line in text.splitlines():
        fields = line.split()
        if not fields or not fields[0].startswith("cpu"):
            continue
        try:
            values = [int(v) for v in fields[1:]]
        except ValueError:
            continue
        if len(values) < 4:
            continue
        idle = values[3] + (values[4] if len(values) > 4 else 0)  # idle + iowait
        total = sum(values)
        busy = total - idle
        result[fields[0]] = (busy, total)
    return result


def cpu_percent(prev: tuple[int, int], curr: tuple[int, int]) -> float:
    """Compute CPU busy percentage between two (busy, total) samples."""
    busy_delta = curr[0] - prev[0]
    total_delta = curr[1] - prev[1]
    if total_delta <= 0:
        return 0.0
    return max(0.0, min(100.0, 100.0 * busy_delta / total_delta))


def parse_meminfo(text: str) -> dict[str, int]:
    """Parse /proc/meminfo into {key: bytes}. Values in the file are kB."""
    result: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split(":")
        if len(parts) != 2:
            continue
        key = parts[0].strip()
        fields = parts[1].split()
        if not fields:
            continue
        try:
            value = int(fields[0])
        except ValueError:
            continue
        # Values are in kB unless unit-less (e.g. HugePages count).
        if len(fields) > 1 and fields[1].lower() == "kb":
            value *= 1024
        result[key] = value
    return result


def parse_df(text: str) -> list[dict[str, object]]:
    """Parse `df -kP` output into a list of mount dicts (bytes).

    Expects POSIX columns: Filesystem 1024-blocks Used Available Capacity Mount.
    """
    mounts: list[dict[str, object]] = []
    lines = text.splitlines()
    for line in lines[1:]:  # skip header
        fields = line.split()
        if len(fields) < 6:
            continue
        try:
            size = int(fields[1]) * 1024
            used = int(fields[2]) * 1024
            avail = int(fields[3]) * 1024
        except ValueError:
            continue
        mounts.append(
            {
                "filesystem": fields[0],
                "mount": fields[5],
                "size": size,
                "used": used,
                "available": avail,
            }
        )
    return mounts


def parse_net_dev(text: str) -> dict[str, dict[str, int]]:
    """Parse /proc/net/dev into {iface: {rx_bytes, tx_bytes}}."""
    result: dict[str, dict[str, int]] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        name, _, rest = line.partition(":")
        iface = name.strip()
        fields = rest.split()
        if len(fields) < 16:
            continue
        try:
            result[iface] = {"rx_bytes": int(fields[0]), "tx_bytes": int(fields[8])}
        except ValueError:
            continue
    return result


def parse_uptime(text: str) -> float:
    """Parse /proc/uptime; return uptime seconds."""
    fields = text.split()
    if not fields:
        return 0.0
    try:
        return float(fields[0])
    except ValueError:
        return 0.0


def parse_loadavg(text: str) -> dict[str, float | int]:
    """Parse /proc/loadavg into load1/5/15 and process counts."""
    fields = text.split()
    if len(fields) < 5:
        return {}
    result: dict[str, float | int] = {}
    try:
        result["load1"] = float(fields[0])
        result["load5"] = float(fields[1])
        result["load15"] = float(fields[2])
    except ValueError:
        return {}
    running, _, total = fields[3].partition("/")
    try:
        result["procs_running"] = int(running)
        result["procs_total"] = int(total)
    except ValueError:
        pass
    return result


def parse_temp(text: str) -> float | None:
    """Parse a thermal_zone temp file (millidegrees C) into degrees C."""
    text = text.strip()
    if not text:
        return None
    try:
        return int(text) / 1000.0
    except ValueError:
        return None


_TEMP_VALUE_RE = re.compile(r"mValue=([-\d.]+)")
_TEMP_NAME_RE = re.compile(r"mName=([^,}]+)")


def parse_thermal_dumpsys(text: str) -> dict[str, float]:
    """Parse `dumpsys thermalservice` HAL temperatures into {name: celsius}.

    Reads the "Current temperatures from HAL" block (live values already in C).
    Falls back to the "Cached temperatures" block if the HAL block is absent.
    Non-root friendly, unlike /sys/class/thermal which needs elevated access.
    """
    hal = _thermal_block(text, "Current temperatures from HAL")
    cached = _thermal_block(text, "Cached temperatures")
    return hal or cached


def _thermal_block(text: str, header: str) -> dict[str, float]:
    result: dict[str, float] = {}
    in_block = False
    for line in text.splitlines():
        if header in line:
            in_block = True
            continue
        if not in_block:
            continue
        if "Temperature{" not in line:
            break  # end of the block
        value = _TEMP_VALUE_RE.search(line)
        name = _TEMP_NAME_RE.search(line)
        if value and name:
            try:
                result[name.group(1).strip()] = float(value.group(1))
            except ValueError:
                continue
    return result


def parse_hz(text: str) -> int | None:
    """Parse a single-integer sysfs file (e.g. scaling_cur_freq in kHz)."""
    text = text.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


_GPU_GLOBAL_RE = re.compile(r"Global total:\s*(\d+)")


def parse_gpu_meminfo(text: str) -> int | None:
    """Parse `dumpsys gpu` for the global total GPU memory in bytes.

    Returns None if the line is absent (e.g. no GPU memory tracking).
    """
    match = _GPU_GLOBAL_RE.search(text)
    if not match:
        return None
    return int(match.group(1))


def parse_battery(text: str) -> dict[str, float]:
    """Parse `dumpsys battery` into stable power-state fields.

    Returns any of: ac_online, usb_online (1/0), voltage_volts (from mV),
    charge_counter, level, temperature_celsius (from tenths). Missing fields
    are simply omitted.
    """
    fields: dict[str, float] = {}
    for line in text.splitlines():
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if not value:
            continue
        if key == "ac powered":
            fields["ac_online"] = 1.0 if value == "true" else 0.0
        elif key == "usb powered":
            fields["usb_online"] = 1.0 if value == "true" else 0.0
        elif key == "voltage":
            _maybe(fields, "voltage_volts", value, scale=0.001)  # mV -> V
        elif key == "charge counter":
            _maybe(fields, "charge_counter", value)
        elif key == "level":
            _maybe(fields, "level", value)
        elif key == "temperature":
            _maybe(fields, "temperature_celsius", value, scale=0.1)  # tenths C
    return fields


def _maybe(fields: dict[str, float], name: str, raw: str, scale: float = 1.0) -> None:
    try:
        fields[name] = float(raw) * scale
    except ValueError:
        pass
