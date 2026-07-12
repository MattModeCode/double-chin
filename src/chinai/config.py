"""Filesystem configuration and constants for ChinAI."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

SAMPLE_RATE = 24000
MIN_REFERENCE_SECONDS = 5.0
MAX_REFERENCE_SECONDS = 20.0

# ChinAI was built on top of an earlier local prototype whose data lived
# under this path. `migrate_legacy_home` carries it forward one time so a
# rename doesn't orphan anything already recorded.
_LEGACY_HOME = Path.home() / ".myna"


def chinai_home() -> Path:
    """Return the ChinAI home directory, honouring the CHINAI_HOME env override."""
    env_value = os.environ.get("CHINAI_HOME")
    if env_value:
        return Path(env_value).expanduser()
    return Path.home() / ".chinai"


def migrate_legacy_home() -> Path | None:
    """Move a pre-rename legacy home directory into place, once.

    Only touches the default location: if CHINAI_HOME is set, or the
    default home already exists, or there's no legacy directory to bring
    over, this is a no-op. Returns the migrated path if a migration
    happened, else None. Call this from entry points that actually use
    storage (CLI commands, the desktop app) — not from pure accessors like
    `chinai_home()`, so it never runs as a side effect of just reading a path.
    """
    if os.environ.get("CHINAI_HOME"):
        return None
    home = chinai_home()
    if home.exists() or not _LEGACY_HOME.is_dir():
        return None
    try:
        os.rename(_LEGACY_HOME, home)
    except OSError:
        # Cross-device rename (e.g. legacy home on a different volume):
        # fall back to a copy so nothing is lost even without an atomic move.
        shutil.copytree(_LEGACY_HOME, home)
    return home


def voices_dir() -> Path:
    """Return the directory where enrolled voices are stored."""
    return chinai_home() / "voices"


def ensure_dir(path: Path) -> Path:
    """Create `path` (and any missing parents) if needed, and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_chinai_home() -> Path:
    """Ensure the ChinAI home directory exists and return it."""
    return ensure_dir(chinai_home())


def ensure_voices_dir() -> Path:
    """Ensure the voices directory exists and return it."""
    return ensure_dir(voices_dir())
