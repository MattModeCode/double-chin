"""Generation history persistence for Myna Studio.

Every completed generation appends one JSON object to
`MYNA_HOME/studio/history.jsonl`; the audio itself lives in
`MYNA_HOME/studio/jobs/<job_id>/out.wav`. Append-only, newest last on
disk, returned newest first.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from myna.config import ensure_dir, myna_home


def studio_dir() -> Path:
    """Return the Studio state directory under the Myna home."""
    return myna_home() / "studio"


def jobs_dir() -> Path:
    """Return the directory holding per-job output folders."""
    return studio_dir() / "jobs"


def job_dir(job_id: str) -> Path:
    """Return (and create) the output folder for one job."""
    return ensure_dir(jobs_dir() / job_id)


def history_path() -> Path:
    return studio_dir() / "history.jsonl"


def append_record(record: dict[str, Any]) -> None:
    """Append one completed-generation record to the history file."""
    ensure_dir(studio_dir())
    with history_path().open("a") as handle:
        handle.write(json.dumps(record) + "\n")


def read_history() -> list[dict[str, Any]]:
    """Return all history records, newest first.

    Lines that fail to parse are skipped rather than poisoning the whole
    history — a truncated final line (e.g. after a crash mid-append) must
    not take the application down.
    """
    path = history_path()
    if not path.is_file():
        return []

    records: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    records.reverse()
    return records


def audio_path(job_id: str) -> Path:
    """Return the expected output wav path for a job id."""
    return jobs_dir() / job_id / "out.wav"
