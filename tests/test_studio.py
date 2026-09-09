"""Offline tests for the Double Chin application layer.

A fake engine is injected through the app factory, so the whole HTTP
surface — enrolment, jobs, SSE progress, history, audio serving — runs
in-process with no model, no network, and DOUBLECHIN_HOME pointed at a tmp dir.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from double_chin.engine import SynthesisReport
from double_chin.studio.app import create_app

# TestClient's default Host is "testserver"; the app's local-origin guard
# only trusts loopback, so every client must present a 127.0.0.1 base URL —
# exactly what a real browser hitting `double-chin studio` sends.
_LOCAL_BASE = "http://127.0.0.1:8787"


def _client(app) -> TestClient:
    return TestClient(app, base_url=_LOCAL_BASE)


class FakeEngine:
    """Mimics DoubleChinEngine.synthesize: two chunks, writes a tiny wav."""

    def __init__(self, block_on: threading.Event | None = None) -> None:
        self.block_on = block_on
        self.calls: list[dict] = []

    def synthesize(self, script, reference_wav, out_path, progress=None, **params):
        self.calls.append({"script": script, "params": params})
        if self.block_on is not None:
            self.block_on.wait(timeout=10)

        chunks = ["chunk one text", "chunk two text"]
        for index, text in enumerate(chunks, start=1):
            if progress is not None:
                progress(index, len(chunks), text)

        import torch
        import torchaudio

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        torchaudio.save(str(out_path), torch.zeros(1, 2400), 24000)

        return SynthesisReport(
            chunk_count=len(chunks),
            audio_seconds=0.1,
            wall_seconds=0.01,
            speed_ratio=10.0,
            device="cpu",
            out_path=out_path,
        )


class ExplodingEngine:
    def synthesize(self, **kwargs):
        raise RuntimeError("engine went sideways")


def _write_wav(path: Path, seconds: float) -> Path:
    import torch
    import torchaudio

    torchaudio.save(str(path), torch.zeros(1, int(24000 * seconds)), 24000)
    return path


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.setenv("DOUBLECHIN_HOME", str(tmp_path / "home"))
    engine = FakeEngine()
    app = create_app(
        engine_factory=lambda: engine,
        verify_fn=lambda ref, out: 0.87,
        verdict_fn=lambda score: "strong match",
    )
    return _client(app), engine, tmp_path


def _enroll_test_voice(tmp_path, name="testvoice"):
    from double_chin.voices import enroll

    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    clips = [
        _write_wav(src / "a.wav", 6.0),
        _write_wav(src / "b.wav", 2.0),
    ]
    return enroll(name, clips)


def _run_job(client, voice="testvoice", text="Hello there. General script."):
    response = client.post("/api/jobs", json={"voice": voice, "text": text})
    assert response.status_code == 202
    return response.json()["job_id"]


def _wait_done(client, job_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = client.get(f"/api/jobs/{job_id}").json()
        if snapshot["status"] in ("done", "error"):
            return snapshot
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


def test_voices_empty_then_listed(studio, tmp_path):
    client, _engine, _ = studio
    assert client.get("/api/voices").json() == []

    _enroll_test_voice(tmp_path)
    voices = client.get("/api/voices").json()
    assert len(voices) == 1
    assert voices[0]["name"] == "testvoice"
    assert voices[0]["has_holdout"] is True


def test_enroll_via_upload(studio, tmp_path):
    client, _engine, _ = studio
    clip = _write_wav(tmp_path / "upload.wav", 6.0)

    with clip.open("rb") as handle:
        response = client.post(
            "/api/voices",
            data={"name": "uploaded"},
            files=[("files", ("upload.wav", handle, "audio/wav"))],
        )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "uploaded"
    assert body["has_holdout"] is False  # single clip: nothing to hold out


def test_enroll_rejects_bad_name(studio, tmp_path):
    client, _engine, _ = studio
    clip = _write_wav(tmp_path / "u.wav", 6.0)
    with clip.open("rb") as handle:
        response = client.post(
            "/api/voices",
            data={"name": "Bad Name!"},
            files=[("files", ("u.wav", handle, "audio/wav"))],
        )
    assert response.status_code == 400
    assert "invalid voice name" in response.json()["detail"]


def test_job_unknown_voice_404(studio):
    client, _engine, _ = studio
    response = client.post("/api/jobs", json={"voice": "ghost", "text": "hi"})
    assert response.status_code == 404


def test_job_empty_text_422(studio):
    client, _engine, _ = studio
    response = client.post("/api/jobs", json={"voice": "x", "text": ""})
    assert response.status_code == 422


def test_job_happy_path_events_history_audio(studio, tmp_path):
    client, engine, _ = studio
    _enroll_test_voice(tmp_path)
    job_id = _run_job(client)

    # SSE stream: replay from the start, follow to the terminal event.
    kinds: list[str] = []
    payloads: list[dict] = []
    with client.stream("GET", f"/api/jobs/{job_id}/events") as stream:
        current_kind = None
        for line in stream.iter_lines():
            if line.startswith("event: "):
                current_kind = line[len("event: "):]
            elif line.startswith("data: ") and current_kind:
                kinds.append(current_kind)
                payloads.append(json.loads(line[len("data: "):]))
                if current_kind in ("done", "error"):
                    break

    assert kinds == ["queued", "progress", "progress", "verifying", "done"]
    progress_events = [p for k, p in zip(kinds, payloads) if k == "progress"]
    assert progress_events[0] == {"chunk": 1, "total": 2, "text": "chunk one text"}

    done = payloads[-1]
    assert done["similarity"] == 0.87
    assert done["verdict"] == "strong match"
    assert done["compared_against"] == "holdout"
    assert done["chunk_count"] == 2

    # Params passed through to the engine (defaults + explicit seed=None).
    assert engine.calls[0]["params"]["exaggeration"] == 0.5

    # History reflects the run and the audio is downloadable.
    records = client.get("/api/history").json()
    assert len(records) == 1
    assert records[0]["id"] == job_id
    assert records[0]["audio_available"] is True

    audio = client.get(f"/api/audio/{job_id}")
    assert audio.status_code == 200
    assert audio.headers["content-type"] == "audio/wav"
    assert len(audio.content) > 44  # more than a wav header


def test_second_job_while_running_409(tmp_path, monkeypatch):
    monkeypatch.setenv("DOUBLECHIN_HOME", str(tmp_path / "home"))
    gate = threading.Event()
    app = create_app(
        engine_factory=lambda: FakeEngine(block_on=gate),
        verify_fn=None,
    )
    client = _client(app)
    _enroll_test_voice(tmp_path)

    first = _run_job(client)
    response = client.post(
        "/api/jobs", json={"voice": "testvoice", "text": "second"}
    )
    assert response.status_code == 409

    gate.set()
    snapshot = _wait_done(client, first)
    assert snapshot["status"] == "done"
    # With verification disabled the record still lands, unverified.
    assert snapshot["result"]["similarity"] is None


def test_engine_failure_surfaces_as_error_event(tmp_path, monkeypatch):
    monkeypatch.setenv("DOUBLECHIN_HOME", str(tmp_path / "home"))
    app = create_app(engine_factory=ExplodingEngine, verify_fn=None)
    client = _client(app)
    _enroll_test_voice(tmp_path)

    job_id = _run_job(client)
    snapshot = _wait_done(client, job_id)
    assert snapshot["status"] == "error"
    assert "engine went sideways" in snapshot["error"]

    # Failed runs never reach the history file.
    assert client.get("/api/history").json() == []


def test_events_unknown_job_404(studio):
    client, _engine, _ = studio
    assert client.get("/api/jobs/nope/events").status_code == 404
    assert client.get("/api/jobs/nope").status_code == 404


def test_audio_missing_and_invalid_ids(studio):
    client, _engine, _ = studio
    assert client.get("/api/audio/deadbeef0000").status_code == 404
    assert client.get("/api/audio/not-alnum!").status_code == 400


def test_doctor_reports_environment(studio):
    client, _engine, _ = studio
    doctor = client.get("/api/doctor").json()
    assert doctor["voices"] == 0
    assert doctor["device"] in ("mps", "cuda", "cpu", None)
    assert "double_chin_home" in doctor


def test_index_served(studio):
    client, _engine, _ = studio
    response = client.get("/")
    assert response.status_code == 200
    assert "Double Chin" in response.text


def test_job_text_over_limit_422(studio):
    client, _engine, _ = studio
    huge = "a" * 20_001
    response = client.post("/api/jobs", json={"voice": "x", "text": huge})
    assert response.status_code == 422


def test_job_rate_out_of_range_422(studio, tmp_path):
    client, _engine, _ = studio
    _enroll_test_voice(tmp_path)
    too_slow = client.post(
        "/api/jobs", json={"voice": "testvoice", "text": "hi", "rate": 0.1}
    )
    too_fast = client.post(
        "/api/jobs", json={"voice": "testvoice", "text": "hi", "rate": 5.0}
    )
    assert too_slow.status_code == 422
    assert too_fast.status_code == 422


def test_job_rate_passed_through_to_engine(studio, tmp_path):
    client, engine, _ = studio
    _enroll_test_voice(tmp_path)
    job_id = _run_job(client)
    _wait_done(client, job_id)
    # Defaults still include rate; an explicit value threads through params.
    assert engine.calls[0]["params"]["rate"] == 1.0


def test_enroll_collision_then_overwrite(studio, tmp_path):
    client, _engine, _ = studio
    _enroll_test_voice(tmp_path, name="dupe")

    clip = _write_wav(tmp_path / "again.wav", 6.0)
    with clip.open("rb") as handle:
        blocked = client.post(
            "/api/voices",
            data={"name": "dupe"},
            files=[("files", ("again.wav", handle, "audio/wav"))],
        )
    assert blocked.status_code == 409

    with clip.open("rb") as handle:
        forced = client.post(
            "/api/voices",
            data={"name": "dupe", "overwrite": "true"},
            files=[("files", ("again.wav", handle, "audio/wav"))],
        )
    assert forced.status_code == 201


def test_enroll_too_many_files(studio, tmp_path):
    client, _engine, _ = studio
    clip = _write_wav(tmp_path / "one.wav", 6.0)
    files = []
    handles = []
    try:
        for i in range(25):  # cap is 24
            handle = clip.open("rb")
            handles.append(handle)
            files.append(("files", (f"c{i}.wav", handle, "audio/wav")))
        response = client.post("/api/voices", data={"name": "many"}, files=files)
    finally:
        for handle in handles:
            handle.close()
    assert response.status_code == 400
    assert "too many files" in response.json()["detail"]


def test_cross_origin_and_bad_host_refused(studio):
    client, _engine, _ = studio
    # A cross-origin browser POST is refused even though it would be "sent".
    cross = client.post(
        "/api/jobs",
        json={"voice": "x", "text": "hi"},
        headers={"origin": "http://evil.example"},
    )
    assert cross.status_code == 403

    # A rebound DNS name (non-loopback Host) is refused.
    rebind = client.get("/api/voices", headers={"host": "attacker.example"})
    assert rebind.status_code == 403

    # Same-origin localhost is allowed through the guard.
    ok = client.get("/api/voices", headers={"origin": "http://127.0.0.1:8787"})
    assert ok.status_code == 200


def test_sse_replay_from_cursor(studio, tmp_path):
    """A late consumer replays every event from the start, including done."""
    client, _engine, _ = studio
    _enroll_test_voice(tmp_path)
    job_id = _run_job(client)
    _wait_done(client, job_id)  # job fully finished before we open the stream

    kinds = []
    with client.stream("GET", f"/api/jobs/{job_id}/events") as stream:
        current = None
        for line in stream.iter_lines():
            if line.startswith("event: "):
                current = line[len("event: "):]
            elif line.startswith("data: ") and current:
                kinds.append(current)
                if current in ("done", "error"):
                    break
    assert kinds == ["queued", "progress", "progress", "verifying", "done"]


def test_history_skips_corrupt_lines(tmp_path, monkeypatch):
    monkeypatch.setenv("DOUBLECHIN_HOME", str(tmp_path / "home"))
    from double_chin.studio import history

    history.append_record({"id": "good1", "voice": "v"})
    # Simulate a torn record (crash mid-append) that still ended in a
    # newline before the next good record landed on its own line.
    with history.history_path().open("a") as handle:
        handle.write('{"id": "good2", "vo\n')
    history.append_record({"id": "good3", "voice": "v"})

    records = history.read_history()
    ids = [r["id"] for r in records]
    assert ids == ["good3", "good1"]  # corrupt middle line skipped, newest first


def test_jobs_pruned_to_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("DOUBLECHIN_HOME", str(tmp_path / "home"))
    from double_chin.studio.jobs import _MAX_RETAINED_JOBS, JobManager

    app = create_app(
        engine_factory=lambda: FakeEngine(),
        verify_fn=None,
    )
    manager: JobManager = app.state.manager
    client = _client(app)
    _enroll_test_voice(tmp_path)

    for _ in range(_MAX_RETAINED_JOBS + 5):
        job_id = _run_job(client)
        _wait_done(client, job_id)

    assert len(manager._jobs) <= _MAX_RETAINED_JOBS


def test_delivery_serves_the_opening_profile_and_the_neutral_baseline(studio):
    client, _engine, _ = studio
    from double_chin.delivery import NEUTRAL_PROFILE, TUNED_PROFILE

    payload = client.get("/api/delivery").json()

    assert payload["defaults"] == TUNED_PROFILE.as_dict()  # no saved file yet
    assert payload["neutral"] == NEUTRAL_PROFILE.as_dict()
    assert set(payload["defaults"]) == {"exaggeration", "cfg_weight", "temperature", "rate"}


def test_delivery_defaults_reflect_a_saved_profile(studio):
    client, _engine, _ = studio
    from double_chin.delivery import TUNED_PROFILE, DeliveryProfile, save_defaults

    saved = DeliveryProfile(0.3, 0.75, 0.6, 0.95)
    save_defaults(saved)

    payload = client.get("/api/delivery").json()
    assert payload["defaults"] == saved.as_dict()
    assert payload["defaults"] != TUNED_PROFILE.as_dict()
    assert payload["neutral"] != saved.as_dict()  # reset still goes somewhere else


def test_delivery_defaults_survive_a_corrupt_file(studio):
    client, _engine, _ = studio
    from double_chin.delivery import TUNED_PROFILE, defaults_path

    defaults_path().parent.mkdir(parents=True, exist_ok=True)
    defaults_path().write_text("}{")

    payload = client.get("/api/delivery").json()
    assert payload["defaults"] == TUNED_PROFILE.as_dict()


def test_delivery_values_are_accepted_by_the_jobs_endpoint(studio, tmp_path):
    client, engine, _ = studio
    _enroll_test_voice(tmp_path)

    payload = client.get("/api/delivery").json()
    for name in ("defaults", "neutral"):
        response = client.post(
            "/api/jobs", json={"voice": "testvoice", "text": "A line.", **payload[name]}
        )
        assert response.status_code == 202, f"{name} rejected: {response.text}"
        _wait_done(client, response.json()["job_id"])

    assert engine.calls[0]["params"]["cfg_weight"] == payload["defaults"]["cfg_weight"]


def test_every_element_id_the_frontend_touches_exists_in_the_page():
    """`$("some-id")` in app.js must name a real element in index.html.

    The studio frontend has no test runner of its own, so a renamed or
    forgotten id would otherwise only surface as a dead button in the browser.
    """
    import re

    static = Path(__file__).resolve().parents[1] / "src" / "double_chin" / "studio" / "static"
    script = (static / "app.js").read_text()
    markup = (static / "index.html").read_text()

    referenced = set(re.findall(r'\$\("([a-z0-9-]+)"\)', script))
    # Some elements are built by app.js itself (the empty-state link), so ids
    # it assigns count as declared too.
    declared = set(re.findall(r'id="([a-z0-9-]+)"', markup))
    declared |= set(re.findall(r'id:\s*"([a-z0-9-]+)"', script))

    missing = sorted(referenced - declared)
    assert not missing, f"app.js references ids that index.html does not define: {missing}"


def test_delivery_knob_ids_have_a_numeric_readout_each():
    """Every slider id also needs its `<id>-val` output, which syncDelivery writes."""
    import re

    static = Path(__file__).resolve().parents[1] / "src" / "double_chin" / "studio" / "static"
    script = (static / "app.js").read_text()
    markup = (static / "index.html").read_text()

    block = re.search(r"const KNOB_FIELDS = Object\.freeze\(\{(.+?)\}\)", script, re.S)
    knob_ids = re.findall(r"^\s*([a-z_]+):", block.group(1), re.M)
    assert knob_ids, "KNOB_FIELDS is empty; the delivery panel would never sync"

    declared = set(re.findall(r'id="([a-z0-9-]+)"', markup))
    for knob_id in knob_ids:
        assert knob_id in declared, f"no slider with id {knob_id}"
        assert f"{knob_id}-val" in declared, f"no readout with id {knob_id}-val"
