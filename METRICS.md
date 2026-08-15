# Metrics Reference

All metrics are prefixed with `androidtv_` and carry a `device` label (the ADB
serial, e.g. `192.168.0.27:5555`). Metrics are collected by a background thread
per device and served from cache on each Prometheus scrape.

Identifying labels (Android version, model, ...) are not repeated on every metric.
They live once on `androidtv_device_info`; join to it in queries when needed.

## Identity & availability

| Metric                  | Type  | Labels                                                                | Unit | Source             | Description                                                                                             |
| ----------------------- | ----- | --------------------------------------------------------------------- | ---- | ------------------ | ------------------------------------------------------------------------------------------------------- |
| `androidtv_device_info` | Gauge | `device`, `android_version`, `model`, `manufacturer`, `name`, `board` | 1    | `getprop`          | Static device identity. Value is always `1`; the information is in the labels. Fetched once and cached. |
| `androidtv_up`          | Gauge | `device`                                                              | bool | reachability check | `1` if the device was reachable at the last collection cycle, else `0`.                                 |

## CPU

| Metric                          | Type  | Labels          | Unit    | Source                              | Description                                                                                                                                                           |
| ------------------------------- | ----- | --------------- | ------- | ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `androidtv_cpu_usage_percent`   | Gauge | `device`, `cpu` | percent | `/proc/stat`                        | CPU busy percentage. `cpu="cpu"` is the aggregate; `cpu="cpuN"` is per core. Computed from the delta between two polls, so the first cycle after start emits nothing. |
| `androidtv_cpu_frequency_hertz` | Gauge | `device`, `cpu` | hertz   | `/sys/.../cpufreq/scaling_cur_freq` | Current clock frequency per core (`cpu="cpuN"`). Read in kHz and converted to Hz.                                                                                     |

## Memory

| Metric                   | Type  | Labels            | Unit  | Source          | Description                                                                                                                |
| ------------------------ | ----- | ----------------- | ----- | --------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `androidtv_memory_bytes` | Gauge | `device`, `field` | bytes | `/proc/meminfo` | Memory statistics. `field` is one of `total`, `available`, `free`, `buffers`, `cached`. Values converted from kB to bytes. |

## Disk

| Metric                 | Type  | Labels                     | Unit  | Source   | Description                                                                      |
| ---------------------- | ----- | -------------------------- | ----- | -------- | -------------------------------------------------------------------------------- |
| `androidtv_disk_bytes` | Gauge | `device`, `mount`, `field` | bytes | `df -kP` | Filesystem usage per mount point. `field` is one of `size`, `used`, `available`. |

## Thermal

| Metric                          | Type  | Labels           | Unit | Source                   | Description                                                                                                                                                                                                                                                            |
| ------------------------------- | ----- | ---------------- | ---- | ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `androidtv_temperature_celsius` | Gauge | `device`, `zone` | °C   | `dumpsys thermalservice` | Temperature per named HAL zone (e.g. `soc_max`, `board_ddr`, `board_wifi`, `board_soc_bottom`). Uses the live "Current temperatures from HAL" block, falling back to "Cached temperatures". `/sys/class/thermal` is not used because it requires root on many devices. |

## Network

| Metric                                   | Type    | Labels                | Unit  | Source          | Description                      |
| ---------------------------------------- | ------- | --------------------- | ----- | --------------- | -------------------------------- |
| `androidtv_network_receive_bytes_total`  | Counter | `device`, `interface` | bytes | `/proc/net/dev` | Bytes received per interface.    |
| `androidtv_network_transmit_bytes_total` | Counter | `device`, `interface` | bytes | `/proc/net/dev` | Bytes transmitted per interface. |

Counters are incremented by the per-poll delta. If a counter goes backwards
(device reboot / kernel counter reset), the current value is used as the increment.

## System

| Metric                     | Type  | Labels             | Unit    | Source          | Description                                                       |
| -------------------------- | ----- | ------------------ | ------- | --------------- | ----------------------------------------------------------------- |
| `androidtv_uptime_seconds` | Gauge | `device`           | seconds | `/proc/uptime`  | Device uptime.                                                    |
| `androidtv_load_average`   | Gauge | `device`, `period` | load    | `/proc/loadavg` | System load average. `period` is one of `1`, `5`, `15` (minutes). |
| `androidtv_processes`      | Gauge | `device`, `state`  | count   | `/proc/loadavg` | Process counts. `state` is `running` or `total`.                  |

## GPU (best-effort)

| Metric                       | Type  | Labels   | Unit  | Source        | Description                                                                    |
| ---------------------------- | ----- | -------- | ----- | ------------- | ------------------------------------------------------------------------------ |
| `androidtv_gpu_memory_bytes` | Gauge | `device` | bytes | `dumpsys gpu` | Total GPU memory in use ("Global total"). Emitted only if the line is present. |

GPU frequency and utilisation are **not** collected: on the Google TV Streamer
(and many boxes) `/sys/class/devfreq/*` requires root. This may be revisited for
rooted devices or vendors that expose it unprivileged.

## Power (best-effort)

| Metric                   | Type  | Labels             | Unit | Source            | Description                                                                                              |
| ------------------------ | ----- | ------------------ | ---- | ----------------- | -------------------------------------------------------------------------------------------------------- |
| `androidtv_power_online` | Gauge | `device`, `source` | bool | `dumpsys battery` | Power source online state. `source` is `ac` or `usb`; value `1`/`0`. Detects mains power loss / reboots. |

**Deliberately not exported:** the battery service on a mains-powered box reports
placeholder values (`present: false`, static `voltage: 4200` mV, `temperature: 250`,
`Charge counter: 3000000`). These are hardcoded defaults, not real sensors, so they
are parsed but not turned into metrics to avoid misleading dashboards. Real power
draw in watts requires root access to `/sys/class/power_supply`.

## Collector meta

| Metric                               | Type    | Labels   | Unit    | Source   | Description                                                                                   |
| ------------------------------------ | ------- | -------- | ------- | -------- | --------------------------------------------------------------------------------------------- |
| `androidtv_collect_duration_seconds` | Gauge   | `device` | seconds | internal | Duration of the last successful collection cycle.                                             |
| `androidtv_collect_errors_total`     | Counter | `device` | count   | internal | Number of failed collection cycles. Increments when a device is unreachable or a poll raises. |

## Notes on portability

- Core metrics come from `/proc`, `/sys` and `df`, which are kernel-stable ABIs
  and portable across Android versions and TV boxes.
- `dumpsys`-based metrics (`temperature`, `gpu_memory`, `power_online`) are used
  only where the stable sources need root. These are more coupled to the Android
  version and vendor, and are treated as best-effort (skipped silently if absent).
- All values are verified on a Google TV Streamer (Android 14, board `kirkwood`).
