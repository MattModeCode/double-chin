"""Delivery profiles: the four knobs, their tuned values, and where they persist.

The engine exposes four delivery controls (exaggeration, cfg_weight,
temperature, rate) as bare defaults. This module gives them a name, a
validated shape, and two named profiles:

* `NEUTRAL_PROFILE` — Chatterbox's own baseline, what "Reset" returns to.
* `TUNED_PROFILE` — the outcome of the sweep in `docs/tuning.md`, which is
  what Studio opens with and what "Match my voice" restores. On the owner's
  own corpus that sweep came back a tie, so the two profiles currently hold
  the same values; `tune --write-defaults` is how a different corpus moves
  the opening profile without touching this constant.

The user can save their own defaults over the tuned profile
(`~/.double-chin/delivery.json`); a missing, corrupt, or out-of-range file
falls back to `TUNED_PROFILE` with a logged reason rather than failing, since
a bad settings file must never stop the app from opening.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from double_chin.config import double_chin_home, ensure_double_chin_home
from double_chin.engine import (
    DEFAULT_CFG_WEIGHT,
    DEFAULT_EXAGGERATION,
    DEFAULT_RATE,
    DEFAULT_TEMPERATURE,
    MAX_RATE,
    MIN_RATE,
)

_log = logging.getLogger(__name__)

DEFAULTS_FILENAME = "delivery.json"

# (minimum, maximum, inclusive-minimum) per field, mirroring the bounds the
# Studio API already enforces in `studio/app.py` — temperature is the one
# exclusive lower bound, since 0 is not a usable sampling temperature.
_BOUNDS = {
    "exaggeration": (0.0, 1.0, True),
    "cfg_weight": (0.0, 1.0, True),
    "temperature": (0.0, 2.0, False),
    "rate": (MIN_RATE, MAX_RATE, True),
}


@dataclass(frozen=True)
class DeliveryProfile:
    """One complete set of delivery-knob values."""

    exaggeration: float
    cfg_weight: float
    temperature: float
    rate: float

    def as_dict(self) -> dict[str, float]:
        return asdict(self)

    def validate(self) -> None:
        """Raise ValueError if any field is non-numeric or out of range."""
        for name, (low, high, inclusive) in _BOUNDS.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a number, got {value!r}")
            too_low = value < low if inclusive else value <= low
            if too_low or value > high:
                edge = ">=" if inclusive else ">"
                raise ValueError(
                    f"{name} must be {edge} {low} and <= {high}, got {value}"
                )

    @classmethod
    def from_mapping(cls, data) -> "DeliveryProfile":
        """Build a validated profile from a mapping, ignoring unknown keys.

        Raises:
            ValueError: if a field is missing, non-numeric, or out of range.
        """
        if not isinstance(data, dict):
            raise ValueError(f"expected an object of delivery values, got {type(data)}")
        missing = [name for name in _BOUNDS if name not in data]
        if missing:
            raise ValueError(f"missing delivery values: {', '.join(missing)}")

        profile = cls(**{name: data[name] for name in _BOUNDS})
        profile.validate()
        return profile


# Chatterbox's own baseline. "Reset to defaults" returns here, so the user
# always has one keystroke back to untuned behaviour.
NEUTRAL_PROFILE = DeliveryProfile(
    exaggeration=DEFAULT_EXAGGERATION,
    cfg_weight=DEFAULT_CFG_WEIGHT,
    temperature=DEFAULT_TEMPERATURE,
    rate=DEFAULT_RATE,
)

# Outcome of the sweep against the owner's real recordings (docs/tuning.md):
# no setting of expression, adherence or variation beat the neutral baseline
# on held-out text — every difference sat inside run-to-run noise — so the
# tuned profile *is* the baseline for those three. `rate` is the one knob with
# a large, unambiguous result: any value other than 1.0 wrecks speaker
# similarity (0.67 -> 0.39 at 1.05x), because the time-stretch is applied to
# finished audio. This constant is what Studio opens with and what "Match my
# voice" restores; re-run `double-chin tune --write-defaults` on your own
# recordings to override it per machine.
TUNED_PROFILE = DeliveryProfile(
    exaggeration=0.50,
    cfg_weight=0.50,
    temperature=0.80,
    rate=1.00,
)


def defaults_path() -> Path:
    """Where the user's saved delivery defaults live."""
    return double_chin_home() / DEFAULTS_FILENAME


def load_defaults() -> DeliveryProfile:
    """Return the profile Studio should open with.

    Falls back to `TUNED_PROFILE` — logging why — when no saved file exists,
    or when the one on disk is unreadable, malformed, or out of range.
    """
    path = defaults_path()
    if not path.is_file():
        return TUNED_PROFILE

    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        _log.warning("ignoring unreadable %s: %s", DEFAULTS_FILENAME, exc)
        return TUNED_PROFILE

    try:
        return DeliveryProfile.from_mapping(data)
    except ValueError as exc:
        _log.warning("ignoring invalid %s: %s", DEFAULTS_FILENAME, exc)
        return TUNED_PROFILE


def save_defaults(profile: DeliveryProfile) -> Path:
    """Persist `profile` as the opening defaults, atomically.

    The write goes to a temporary file in the same directory and is renamed
    into place, so an interrupted save can never leave a half-written file
    where the app expects settings.

    Raises:
        ValueError: if the profile is out of range (nothing is written).
        OSError: if the write or rename fails (the previous file survives).
    """
    profile.validate()
    home = ensure_double_chin_home()
    target = defaults_path()

    handle = tempfile.NamedTemporaryFile(
        "w", dir=home, prefix=".delivery-", suffix=".tmp", delete=False
    )
    tmp_path = Path(handle.name)
    try:
        with handle:
            json.dump(profile.as_dict(), handle, indent=2)
            handle.write("\n")
        os.replace(tmp_path, target)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise
    return target


def clear_defaults() -> None:
    """Delete any saved defaults, so the app falls back to `TUNED_PROFILE`."""
    defaults_path().unlink(missing_ok=True)
