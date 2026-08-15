#!/usr/bin/env bash
# Start a local ADB server, then run the exporter. The exporter connects to
# this server (default 127.0.0.1:5037) and bridges to the TV devices over TCP.
set -euo pipefail

adb start-server

exec android-tv-exporter "$@"
