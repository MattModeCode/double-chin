"""The ChinAI application server.

A FastAPI app serving a JSON API plus the single-page frontend in
`static/`. Binds to loopback only (see cli.py): Studio is a personal,
single-user application with no auth layer, so it must never listen on
a routable interface.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from urllib.parse import urlsplit

from chinai import __version__
from chinai.engine import (
    DEFAULT_CFG_WEIGHT,
    DEFAULT_EXAGGERATION,
    DEFAULT_TEMPERATURE,
)
from chinai.studio import history
from chinai.studio.jobs import JobBusyError, JobManager, JobNotFoundError

_STATIC_DIR = Path(__file__).parent / "static"
_SSE_KEEPALIVE_SECONDS = 15.0
_MAX_SCRIPT_CHARS = 20_000
_MAX_ENROLL_FILES = 24
_MAX_ENROLL_BYTES = 200 * 1024 * 1024  # 200 MB total across an enrolment
_LOCAL_HOSTNAMES = frozenset({"127.0.0.1", "localhost", "[::1]", "::1"})


def _hostname_is_local(netloc: str) -> bool:
    """True if `netloc` (host[:port], from a Host or Origin header) is loopback."""
    if not netloc:
        return False
    host = netloc.rsplit(":", 1)[0] if netloc.rsplit(":", 1)[-1].isdigit() else netloc
    return host in _LOCAL_HOSTNAMES


class JobRequest(BaseModel):
    voice: str
    text: str = Field(min_length=1, max_length=_MAX_SCRIPT_CHARS)
    exaggeration: float = Field(default=DEFAULT_EXAGGERATION, ge=0.0, le=1.0)
    cfg_weight: float = Field(default=DEFAULT_CFG_WEIGHT, ge=0.0, le=1.0)
    temperature: float = Field(default=DEFAULT_TEMPERATURE, gt=0.0, le=2.0)
    seed: int | None = None


def _default_engine_factory():
    from chinai.engine import ChinaiEngine

    return ChinaiEngine()


def _default_verify_fn(wav_a, wav_b) -> float:
    from chinai.verify import similarity

    return similarity(wav_a, wav_b)


def _default_verdict_fn(score: float) -> str:
    from chinai.verify import verdict

    return verdict(score)


def create_app(
    engine_factory=None,
    verify_fn=_default_verify_fn,
    verdict_fn=_default_verdict_fn,
) -> FastAPI:
    """Build the Studio app. Tests inject a fake engine via `engine_factory`."""
    app = FastAPI(title="ChinAI", version=__version__)
    manager = JobManager(
        engine_factory=engine_factory or _default_engine_factory,
        verify_fn=verify_fn,
        verdict_fn=verdict_fn,
    )
    app.state.manager = manager

    @app.middleware("http")
    async def local_origin_guard(request: Request, call_next):
        """Reject requests that aren't from the local Studio page.

        Loopback binding stops remote network attackers but not the user's
        own browser: any web page could POST to 127.0.0.1 (cross-origin
        CSRF) or reach us via a rebound DNS name. So we require the Host
        header to be loopback (defeats DNS rebinding) and, when an Origin
        is present, require it to be loopback too (defeats cross-origin
        CSRF). This is the Jupyter/Ollama pattern for a local, auth-less
        single-user server.
        """
        if not _hostname_is_local(request.headers.get("host", "")):
            return JSONResponse(
                {"detail": "host not allowed; Studio serves 127.0.0.1 only"},
                status_code=403,
            )
        origin = request.headers.get("origin")
        if origin is not None and not _hostname_is_local(urlsplit(origin).netloc):
            return JSONResponse(
                {"detail": "cross-origin request refused"}, status_code=403
            )
        return await call_next(request)

    @app.get("/api/voices")
    def get_voices():
        from chinai.voices import list_voices

        return [
            {
                "name": voice.name,
                "duration_seconds": round(voice.duration_seconds, 1),
                "created": voice.created,
                "has_holdout": voice.holdout_wav is not None,
            }
            for voice in list_voices()
        ]

    @app.post("/api/voices", status_code=201)
    async def enroll_voice(
        name: str = Form(...),
        files: list[UploadFile] = File(...),
        overwrite: bool = Form(False),
    ):
        from chinai.config import voices_dir
        from chinai.voices import enroll

        if len(files) > _MAX_ENROLL_FILES:
            raise HTTPException(
                status_code=400,
                detail=f"too many files ({len(files)}); max {_MAX_ENROLL_FILES}.",
            )
        # Guard an existing voice from silent replacement (an enrolment
        # overwrites reference.wav in place); require an explicit opt-in.
        if not overwrite and (voices_dir() / name).is_dir():
            raise HTTPException(
                status_code=409,
                detail=f"voice '{name}' already exists; resend with overwrite=true to replace it.",
            )

        with tempfile.TemporaryDirectory(prefix="chinai-enroll-") as tmp:
            saved: list[Path] = []
            total_bytes = 0
            for index, upload in enumerate(files):
                suffix = Path(upload.filename or f"clip{index}.wav").suffix or ".wav"
                target = Path(tmp) / f"source_{index:02d}{suffix}"
                with target.open("wb") as handle:
                    while chunk := await upload.read(1024 * 1024):
                        total_bytes += len(chunk)
                        if total_bytes > _MAX_ENROLL_BYTES:
                            raise HTTPException(
                                status_code=413,
                                detail="enrolment upload exceeds the size limit.",
                            )
                        handle.write(chunk)
                saved.append(target)

            try:
                info = await asyncio.to_thread(enroll, name, saved)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        return {
            "name": info.name,
            "duration_seconds": round(info.duration_seconds, 1),
            "has_holdout": info.holdout_file is not None,
        }

    @app.post("/api/jobs", status_code=202)
    def create_job(request: JobRequest):
        from chinai.voices import get_voice

        try:
            voice = get_voice(request.voice)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

        params = {
            "exaggeration": request.exaggeration,
            "cfg_weight": request.cfg_weight,
            "temperature": request.temperature,
            "seed": request.seed,
        }
        try:
            job = manager.submit(voice, request.text, params)
        except JobBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

        return {"job_id": job.id, "status": job.status}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        try:
            job = manager.get(job_id)
        except JobNotFoundError:
            raise HTTPException(status_code=404, detail=f"no job {job_id}")
        return {
            "job_id": job.id,
            "status": job.status,
            "voice": job.voice,
            "created": job.created,
            "result": job.result,
            "error": job.error,
        }

    @app.get("/api/jobs/{job_id}/events")
    async def job_events(job_id: str):
        try:
            manager.get(job_id)
        except JobNotFoundError:
            raise HTTPException(status_code=404, detail=f"no job {job_id}")

        async def stream():
            cursor = 0
            while True:
                events, cursor, finished = await asyncio.to_thread(
                    manager.wait_events, job_id, cursor, _SSE_KEEPALIVE_SECONDS
                )
                for event in events:
                    payload = json.dumps(event.data)
                    yield f"event: {event.kind}\ndata: {payload}\n\n"
                if finished:
                    return
                if not events:
                    yield ": keepalive\n\n"

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/history")
    def get_history():
        records = history.read_history()
        for record in records:
            record["audio_available"] = history.audio_path(record["id"]).is_file()
        return records

    @app.get("/api/audio/{job_id}")
    def get_audio(job_id: str, download: bool = False):
        # Job ids are hex strings we minted; reject anything path-like.
        if not job_id.isalnum():
            raise HTTPException(status_code=400, detail="invalid job id")
        path = history.audio_path(job_id)
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"no audio for job {job_id}")
        filename = f"chinai-{job_id}.wav" if download else None
        return FileResponse(path, media_type="audio/wav", filename=filename)

    @app.get("/api/doctor")
    def get_doctor():
        from chinai.config import chinai_home
        from chinai.voices import list_voices

        report: dict = {
            "version": __version__,
            "chinai_home": str(chinai_home()),
            "voices": len(list_voices()),
        }
        try:
            import torch

            if torch.backends.mps.is_available():
                device = "mps"
            elif torch.cuda.is_available():
                device = "cuda"
            else:
                device = "cpu"
            report["torch"] = torch.__version__
            report["device"] = device
        except ImportError:
            report["torch"] = None
            report["device"] = None

        hf_cache = Path.home() / ".cache" / "huggingface"
        report["weights_cached"] = (
            any(hf_cache.rglob("*chatterbox*")) if hf_cache.is_dir() else False
        )
        return report

    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")

    return app
