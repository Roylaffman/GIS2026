"""Shared helpers for the DSHtest GIS pipeline.

Loads API keys / config from the project `.env` file and exposes a few
constants used across the scripts.
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
WEB_DIR = PROJECT_ROOT / "web"

# Mount Mitchell, NC summit (highest point east of the Mississippi)
SUMMIT_LAT = 35.7649
SUMMIT_LON = -82.2651
SUMMIT_NAME = "Mount Mitchell"

# A study box around the summit: ~0.08 deg (~8 km) wide/tall
AOI = {
    "north": SUMMIT_LAT + 0.04,
    "south": SUMMIT_LAT - 0.04,
    "west": SUMMIT_LON - 0.04,
    "east": SUMMIT_LON + 0.04,
}


def fix_proj() -> Path | None:
    """Point PROJ at the venv's bundled proj.db if a conflicting global
    PROJ_LIB is set (e.g. a PostGIS install). Returns the dir used, or None."""
    candidate = PROJECT_ROOT / ".venv" / "Lib" / "site-packages" / "rasterio" / "proj_data"
    if candidate.is_dir() and (candidate / "proj.db").exists():
        os.environ["PROJ_LIB"] = str(candidate)
        return candidate
    return None


def load_env(path: Path | None = None) -> dict[str, str]:
    """Minimal .env parser: KEY=VALUE lines, # comments, no interpolation."""
    env: dict[str, str] = {}
    p = Path(path) if path else PROJECT_ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    # real environment wins over .env
    for k in list(env):
        if k in os.environ and os.environ[k]:
            env[k] = os.environ[k]
    return env


def http_get(url: str, out_path: Path | None = None, timeout: int = 120) -> bytes:
    """urllib GET that follows redirects and writes to out_path if given."""
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "DSHtest-GIS/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)
    return data


if __name__ == "__main__":
    e = load_env()
    print("Keys present:", sorted(e))
