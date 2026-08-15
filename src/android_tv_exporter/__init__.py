"""Generic Prometheus exporter for Android TV devices over ADB."""

from __future__ import annotations

from importlib import metadata

_DIST = "android-tv-exporter"


def _read_version() -> str:
    try:
        return metadata.version(_DIST)
    except metadata.PackageNotFoundError:
        return "0.0.0+dev"


def _read_url() -> str:
    """Return the project's repository/homepage URL from package metadata."""
    try:
        meta = metadata.metadata(_DIST)
    except metadata.PackageNotFoundError:
        return ""
    # Project-URL entries look like "Repository, https://...".
    for entry in meta.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        if label.strip().lower() in ("repository", "homepage"):
            return url.strip()
    return meta.get("Home-page", "")


__version__ = _read_version()
__url__ = _read_url()
