"""Background synthesis jobs for ChinAI.

One job at a time: the engine is a single shared model on one GPU, and
Studio serves a single local user. Submitting while a job runs raises
JobBusyError (surfaced as HTTP 409). Progress flows through an
append-only per-job event list guarded by a Condition, so any number of
SSE consumers can replay from any cursor and follow live — no queue to
drain, no lost final event.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from chinai.studio import history
from chinai.voices import VoiceInfo

TERMINAL_EVENT_KINDS = frozenset({"done", "error"})
_TEXT_PREVIEW_CHARS = 120
# Retain only the most recent finished jobs in memory; persisted history on
# disk (history.jsonl) is the durable record, so this cap just bounds RAM.
_MAX_RETAINED_JOBS = 50


class JobBusyError(RuntimeError):
    """Raised when a synthesis job is already running."""


class JobNotFoundError(KeyError):
    """Raised when a job id is unknown."""


@dataclass
class JobEvent:
    kind: str  # queued | progress | verifying | done | error
    data: dict[str, Any]


@dataclass
class Job:
    id: str
    voice: str
    text: str
    params: dict[str, Any]
    created: str
    status: str = "queued"  # queued | running | done | error
    events: list[JobEvent] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobManager:
    """Owns the engine instance and runs one synthesis job at a time."""

    def __init__(
        self,
        engine_factory: Callable[[], Any],
        verify_fn: Callable[[Any, Any], float] | None = None,
        verdict_fn: Callable[[float], str] | None = None,
    ) -> None:
        self._engine_factory = engine_factory
        self._engine: Any = None
        self._verify_fn = verify_fn
        self._verdict_fn = verdict_fn
        self._jobs: dict[str, Job] = {}
        self._cond = threading.Condition()
        self._worker: threading.Thread | None = None

    def _get_engine(self) -> Any:
        if self._engine is None:
            self._engine = self._engine_factory()
        return self._engine

    @property
    def busy(self) -> bool:
        with self._cond:
            return self._worker is not None and self._worker.is_alive()

    def submit(self, voice: VoiceInfo, text: str, params: dict[str, Any]) -> Job:
        """Start a synthesis job for `text` in `voice`.

        Raises:
            JobBusyError: if another job is still running.
        """
        with self._cond:
            if self._worker is not None and self._worker.is_alive():
                raise JobBusyError("a synthesis job is already running")

            job = Job(
                id=uuid.uuid4().hex[:12],
                voice=voice.name,
                text=text,
                params=dict(params),
                created=_utc_now(),
            )
            self._jobs[job.id] = job
            self._prune_locked()
            self._emit_locked(job, JobEvent("queued", {"job_id": job.id}))

            self._worker = threading.Thread(
                target=self._run, args=(job, voice), daemon=True
            )
            self._worker.start()
            return job

    def get(self, job_id: str) -> Job:
        with self._cond:
            job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        return job

    def wait_events(
        self, job_id: str, cursor: int, timeout: float
    ) -> tuple[list[JobEvent], int, bool]:
        """Return (new events past `cursor`, new cursor, job finished).

        Blocks up to `timeout` seconds waiting for news; an empty batch
        after the timeout is the caller's cue to send an SSE keepalive.
        """
        job = self.get(job_id)
        with self._cond:
            if len(job.events) <= cursor:
                self._cond.wait(timeout)
            events = job.events[cursor:]
            new_cursor = len(job.events)
            finished = job.status in ("done", "error")
        return events, new_cursor, finished

    def _prune_locked(self) -> None:
        """Drop the oldest finished jobs beyond the retention cap.

        Insertion order in the dict is chronological; a running job is
        never evicted (its worker still writes to it).
        """
        removable = [
            jid for jid, job in self._jobs.items()
            if job.status in ("done", "error")
        ]
        overflow = len(self._jobs) - _MAX_RETAINED_JOBS
        for jid in removable[:overflow]:
            del self._jobs[jid]

    def _emit_locked(self, job: Job, event: JobEvent) -> None:
        job.events.append(event)
        self._cond.notify_all()

    def _emit(self, job: Job, event: JobEvent) -> None:
        with self._cond:
            self._emit_locked(job, event)

    def _run(self, job: Job, voice: VoiceInfo) -> None:
        try:
            self._run_inner(job, voice)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            with self._cond:
                job.status = "error"
                job.error = message
                self._emit_locked(job, JobEvent("error", {"message": message}))

    def _run_inner(self, job: Job, voice: VoiceInfo) -> None:
        with self._cond:
            job.status = "running"

        engine = self._get_engine()
        out_path = history.job_dir(job.id) / "out.wav"

        def on_progress(index: int, total: int, text: str) -> None:
            self._emit(
                job,
                JobEvent(
                    "progress",
                    {"chunk": index, "total": total, "text": text},
                ),
            )

        report = engine.synthesize(
            script=job.text,
            reference_wav=voice.reference_wav,
            out_path=out_path,
            progress=on_progress,
            **job.params,
        )

        similarity_score: float | None = None
        verdict_text: str | None = None
        compared_against: str | None = None
        if self._verify_fn is not None:
            holdout = voice.holdout_wav
            compare_wav = holdout if holdout is not None else voice.reference_wav
            compared_against = "holdout" if holdout is not None else "reference"
            self._emit(job, JobEvent("verifying", {"against": compared_against}))
            similarity_score = self._verify_fn(compare_wav, out_path)
            if self._verdict_fn is not None:
                verdict_text = self._verdict_fn(similarity_score)

        record = {
            "id": job.id,
            "created": job.created,
            "voice": job.voice,
            "text_preview": job.text[:_TEXT_PREVIEW_CHARS],
            "chars": len(job.text),
            "chunk_count": report.chunk_count,
            "audio_seconds": round(report.audio_seconds, 2),
            "wall_seconds": round(report.wall_seconds, 2),
            "device": report.device,
            "params": job.params,
            "similarity": (
                round(similarity_score, 3) if similarity_score is not None else None
            ),
            "verdict": verdict_text,
            "compared_against": compared_against,
        }
        history.append_record(record)

        with self._cond:
            job.status = "done"
            job.result = record
            self._emit_locked(job, JobEvent("done", record))
