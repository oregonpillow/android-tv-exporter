from android_tv_exporter import parsers

PROC_STAT = """\
cpu  100 0 50 800 50 0 0 0 0 0
cpu0 40 0 20 400 20 0 0 0 0 0
cpu1 60 0 30 400 30 0 0 0 0 0
intr 12345
ctxt 67890
"""

MEMINFO = """\
MemTotal:        2000000 kB
MemFree:          500000 kB
MemAvailable:    1200000 kB
Buffers:           10000 kB
Cached:           300000 kB
HugePages_Total:       0
"""

DF = """\
Filesystem     1024-blocks    Used Available Capacity Mounted on
/dev/root         1000000  400000    600000      40% /
tmpfs              500000    1000    499000       1% /dev
badline
"""

NET_DEV = """\
Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo:    1234      10    0    0    0     0          0         0     1234      10    0    0    0     0       0          0
  eth0:  555000     100    0    0    0     0          0         0   222000      80    0    0    0     0       0          0
"""

LOADAVG = "0.50 0.40 0.30 2/150 12345\n"


def test_parse_proc_stat():
    result = parsers.parse_proc_stat(PROC_STAT)
    assert set(result) == {"cpu", "cpu0", "cpu1"}
    # cpu: total = 1000, idle+iowait = 800+50 = 850, busy = 150
    assert result["cpu"] == (150, 1000)


def test_cpu_percent():
    prev = (1000, 2000)
    curr = (1500, 3000)  # busy +500, total +1000 -> 50%
    assert parsers.cpu_percent(prev, curr) == 50.0
    # no time passed
    assert parsers.cpu_percent((1000, 2000), (1000, 2000)) == 0.0


def test_parse_meminfo_bytes():
    result = parsers.parse_meminfo(MEMINFO)
    assert result["MemTotal"] == 2000000 * 1024
    assert result["MemAvailable"] == 1200000 * 1024
    assert result["HugePages_Total"] == 0  # unit-less untouched


def test_parse_df():
    mounts = parsers.parse_df(DF)
    assert len(mounts) == 2
    root = mounts[0]
    assert root["mount"] == "/"
    assert root["size"] == 1000000 * 1024
    assert root["used"] == 400000 * 1024


def test_parse_net_dev():
    result = parsers.parse_net_dev(NET_DEV)
    assert result["eth0"]["rx_bytes"] == 555000
    assert result["eth0"]["tx_bytes"] == 222000


def test_parse_uptime():
    assert parsers.parse_uptime("12345.67 98765.43") == 12345.67
    assert parsers.parse_uptime("") == 0.0


def test_parse_loadavg():
    result = parsers.parse_loadavg(LOADAVG)
    assert result["load1"] == 0.50
    assert result["procs_running"] == 2
    assert result["procs_total"] == 150


def test_parse_temp():
    assert parsers.parse_temp("42000") == 42.0
    assert parsers.parse_temp("") is None
    assert parsers.parse_temp("n/a") is None


THERMAL = """\
Thermal Status: 0
Cached temperatures:
        Temperature{mValue=39.9, mType=0, mName=soc_max, mStatus=0}
HAL Ready: true
Current temperatures from HAL:
        Temperature{mValue=37.824, mType=3, mName=board_soc_bottom, mStatus=0}
        Temperature{mValue=40.318, mType=0, mName=soc_max, mStatus=0}
Current cooling devices from HAL:
        CoolingDevice{mValue=0, mType=2, mName=cpufreq-cpu0}
"""


def test_parse_thermal_dumpsys_prefers_hal():
    result = parsers.parse_thermal_dumpsys(THERMAL)
    assert result == {"board_soc_bottom": 37.824, "soc_max": 40.318}


def test_parse_thermal_dumpsys_falls_back_to_cached():
    text = "Cached temperatures:\n        Temperature{mValue=25.5, mType=0, mName=cpu, mStatus=0}\nHAL Ready: true\n"
    assert parsers.parse_thermal_dumpsys(text) == {"cpu": 25.5}


def test_parse_hz():
    assert parsers.parse_hz("1800000") == 1800000
    assert parsers.parse_hz("") is None


GPU_DUMP = """\
Stable Game Driver: unsupported

Memory snapshot for GPU 0:
Global total: 114044928
Proc 506 total: 40960
"""


def test_parse_gpu_meminfo():
    assert parsers.parse_gpu_meminfo(GPU_DUMP) == 114044928
    assert parsers.parse_gpu_meminfo("no gpu here") is None


BATTERY = """\
Current Battery Service state:
  AC powered: true
  USB powered: false
  Charge counter: 3000000
  status: 1
  level: 100
  voltage: 4200
  temperature: 250
"""


def test_parse_battery():
    result = parsers.parse_battery(BATTERY)
    assert result["ac_online"] == 1.0
    assert result["usb_online"] == 0.0
    assert result["voltage_volts"] == 4.2
    assert result["level"] == 100.0
    assert result["temperature_celsius"] == 25.0
    assert result["charge_counter"] == 3000000.0
