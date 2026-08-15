import os

from android_tv_exporter.config import resolve_settings


def test_defaults(monkeypatch):
    for key in list(os.environ):
        if key.startswith("ANDROIDTV_"):
            monkeypatch.delenv(key, raising=False)
    s = resolve_settings(devices=["a:1"])
    assert s.adb_host == "127.0.0.1"
    assert s.adb_port == 5037
    assert s.listen_port == 9100
    assert s.devices == ["a:1"]


def test_env_fallback(monkeypatch):
    monkeypatch.setenv("ANDROIDTV_ADB_HOST", "10.0.0.1")
    monkeypatch.setenv("ANDROIDTV_LISTEN_PORT", "9200")
    monkeypatch.setenv("ANDROIDTV_DEVICES", "x:1, y:2 ,")
    s = resolve_settings()
    assert s.adb_host == "10.0.0.1"
    assert s.listen_port == 9200
    assert s.devices == ["x:1", "y:2"]


def test_cli_wins_over_env(monkeypatch):
    monkeypatch.setenv("ANDROIDTV_ADB_HOST", "10.0.0.1")
    monkeypatch.setenv("ANDROIDTV_LISTEN_PORT", "9200")
    s = resolve_settings(adb_host="192.168.1.1", listen_port=9300, devices=["a:1"])
    assert s.adb_host == "192.168.1.1"
    assert s.listen_port == 9300
