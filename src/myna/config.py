"""Filesystem configuration and constants for Myna."""

from __future__ import annotations

import os
from pathlib import Path

SAMPLE_RATE = 24000
MIN_REFERENCE_SECONDS = 5.0
MAX_REFERENCE_SECONDS = 20.0


def myna_home() -> Path:
    """Return the Myna home directory, honouring the MYNA_HOME env override."""
    env_value = os.environ.get("MYNA_HOME")
    if env_value:
        return Path(env_value).expanduser()
    return Path.home() / ".myna"


def voices_dir() -> Path:
    """Return the directory where enrolled voices are stored."""
    return myna_home() / "voices"


def ensure_dir(path: Path) -> Path:
    """Create `path` (and any missing parents) if needed, and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_myna_home() -> Path:
    """Ensure the Myna home directory exists and return it."""
    return ensure_dir(myna_home())


def ensure_voices_dir() -> Path:
    """Ensure the voices directory exists and return it."""
    return ensure_dir(voices_dir())
