/* ChinAI frontend. Plain JS, no build step, no external requests. */
"use strict";

const $ = (id) => document.getElementById(id);

const state = {
  voices: [],
  jobRunning: false,
  eventSource: null,
  timerHandle: null,
  jobStartedAt: null,
};

/* ---------- bootstrap ---------- */

async function init() {
  wireControls();
  await Promise.all([refreshVoices(), refreshDoctor(), refreshHistory()]);
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch (_) { /* non-JSON error body */ }
    throw new Error(detail);
  }
  return response.json();
}

/* ---------- voices ---------- */

async function refreshVoices(selectName) {
  state.voices = await fetchJson("/api/voices");
  const select = $("voice");
  select.innerHTML = "";
  for (const voice of state.voices) {
    const option = document.createElement("option");
    option.value = voice.name;
    option.textContent = `${voice.name} · ${voice.duration_seconds}s`;
    select.appendChild(option);
  }
  if (selectName) select.value = selectName;
  updateVoiceHint();
  updateGenerateEnabled();
}

function updateVoiceHint() {
  const voice = state.voices.find((v) => v.name === $("voice").value);
  const hint = $("voice-hint");
  if (!voice) {
    hint.textContent = "no voices yet — enroll one from a few recordings";
    return;
  }
  hint.textContent = voice.has_holdout
    ? "verifies against a held-out clip the model never conditions on"
    : "no holdout clip — verification compares against the reference itself";
}

/* ---------- doctor ---------- */

async function refreshDoctor() {
  try {
    const doctor = await fetchJson("/api/doctor");
    const device = doctor.device ? doctor.device.toUpperCase() : "no torch";
    const weights = doctor.weights_cached ? "weights cached" : "first run downloads weights";
    $("env").innerHTML = `<b>${device}</b> · ${weights}`;
    $("version").textContent = `chinai ${doctor.version}`;
  } catch (_) {
    $("env").textContent = "";
  }
}

/* ---------- script stats ---------- */

function updateScriptStats() {
  const text = $("script").value;
  const chars = text.length;
  $("script-stats").textContent = `${chars.toLocaleString()} chars`;
  if (chars > 0) {
    // Rough planning figures: ~15 chars/s spoken, ~0.2x realtime synthesis.
    const audioSeconds = chars / 15;
    const wallSeconds = audioSeconds / 0.2;
    $("eta").textContent =
      `≈ ${formatSeconds(audioSeconds)} of audio · rough synthesis time ${formatSeconds(wallSeconds)}`;
  } else {
    $("eta").textContent = "";
  }
  updateGenerateEnabled();
}

function formatSeconds(total) {
  const seconds = Math.round(total);
  if (seconds < 90) return `${seconds}s`;
  return `${Math.round(seconds / 60)}min`;
}

function updateGenerateEnabled() {
  $("generate").disabled =
    state.jobRunning || !$("voice").value || $("script").value.trim() === "";
}

/* ---------- generate ---------- */

async function generate() {
  const seedRaw = $("seed").value.trim();
  const payload = {
    voice: $("voice").value,
    text: $("script").value,
    exaggeration: parseFloat($("exaggeration").value),
    cfg_weight: parseFloat($("cfg").value),
    temperature: parseFloat($("temperature").value),
    rate: parseFloat($("rate").value),
    seed: seedRaw === "" ? null : parseInt(seedRaw, 10),
  };

  let job;
  try {
    job = await fetchJson("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    showJobError(error.message);
    return;
  }

  beginJobUi();
  followJob(job.job_id);
}

function beginJobUi() {
  state.jobRunning = true;
  state.jobStartedAt = Date.now();
  updateGenerateEnabled();
  $("idle-state").hidden = true;
  $("result").hidden = true;
  $("job-state").hidden = false;
  $("job-error").hidden = true;
  $("chunk-list").innerHTML = "";
  $("bar-fill").style.width = "2%";
  setStatus("model loading…", "");
  state.timerHandle = setInterval(() => {
    const elapsed = Math.round((Date.now() - state.jobStartedAt) / 1000);
    $("job-timer").textContent = `${elapsed}s`;
  }, 1000);
}

function setStatus(text, cls) {
  const status = $("job-status");
  status.textContent = text;
  status.className = `status ${cls}`;
}

function followJob(jobId) {
  const source = new EventSource(`/api/jobs/${jobId}/events`);
  state.eventSource = source;

  source.addEventListener("progress", (event) => {
    const data = JSON.parse(event.data);
    setStatus(`synthesizing chunk ${data.chunk}/${data.total}`, "");
    renderChunk(data);
    $("bar-fill").style.width = `${((data.chunk - 1) / data.total) * 100}%`;
  });

  source.addEventListener("verifying", (event) => {
    const data = JSON.parse(event.data);
    markAllChunksDone();
    $("bar-fill").style.width = "96%";
    setStatus(`verifying speaker similarity (vs ${data.against})…`, "");
  });

  source.addEventListener("done", (event) => {
    const record = JSON.parse(event.data);
    finishJob();
    setStatus("done", "done");
    $("bar-fill").style.width = "100%";
    showResult(record);
    refreshHistory();
  });

  source.addEventListener("error", (event) => {
    // Fired both for server-sent error events (with data) and transport
    // errors (without); a closed stream after "done" also lands here.
    if (event.data) {
      const data = JSON.parse(event.data);
      finishJob();
      setStatus("failed", "error");
      showJobError(data.message);
    } else if (state.jobRunning) {
      finishJob();
      setStatus("connection lost", "error");
      showJobError("Lost the progress stream. The job may still be running — check History shortly.");
    }
  });
}

function renderChunk(data) {
  const list = $("chunk-list");
  markAllChunksDone();
  const item = document.createElement("li");
  item.className = "active";
  item.innerHTML = `<span class="idx">${data.chunk}/${data.total}</span>`;
  item.appendChild(document.createTextNode(data.text));
  list.appendChild(item);
  item.scrollIntoView({ block: "nearest" });
}

function markAllChunksDone() {
  for (const item of $("chunk-list").querySelectorAll("li.active")) {
    item.className = "done-chunk";
  }
}

function finishJob() {
  state.jobRunning = false;
  if (state.eventSource) { state.eventSource.close(); state.eventSource = null; }
  if (state.timerHandle) { clearInterval(state.timerHandle); state.timerHandle = null; }
  updateGenerateEnabled();
}

function showJobError(message) {
  $("idle-state").hidden = true;
  $("job-state").hidden = false;
  const box = $("job-error");
  box.textContent = message;
  box.hidden = false;
}

/* ---------- result ---------- */

function verdictClass(verdict) {
  if (!verdict) return "plain";
  if (verdict.includes("strong")) return "ok";
  if (verdict === "match") return "ok";
  if (verdict === "borderline") return "warn";
  return "err";
}

function showResult(record) {
  $("result").hidden = false;
  const chip = $("verdict-chip");
  if (record.similarity != null) {
    chip.textContent = `${record.similarity.toFixed(3)} · ${record.verdict} (vs ${record.compared_against})`;
    chip.className = `chip ${verdictClass(record.verdict)}`;
  } else {
    chip.textContent = "not verified";
    chip.className = "chip plain";
  }
  $("result-meta").textContent =
    `${record.audio_seconds}s audio · ${record.chunk_count} chunks · ` +
    `${record.wall_seconds}s on ${record.device}`;
  const player = $("player");
  player.src = `/api/audio/${record.id}`;
  $("download").href = `/api/audio/${record.id}?download=true`;
  player.play().catch(() => { /* autoplay may be blocked; the controls remain */ });
}

/* ---------- history ---------- */

async function refreshHistory() {
  const records = await fetchJson("/api/history");
  const container = $("history");
  container.innerHTML = "";
  if (records.length === 0) {
    container.innerHTML = '<div class="empty-hint">nothing generated yet</div>';
    return;
  }
  for (const record of records) {
    const item = document.createElement("div");
    item.className = "item";
    item.setAttribute("role", "button");
    item.tabIndex = 0;

    const text = document.createElement("div");
    text.className = "txt";
    text.textContent = record.text_preview;

    const score = document.createElement("div");
    score.className = "score";
    if (record.similarity != null) {
      score.textContent = record.similarity.toFixed(3);
      score.classList.add(verdictClass(record.verdict));
    }

    const sub = document.createElement("div");
    sub.className = "sub";
    const when = new Date(record.created).toLocaleString();
    sub.textContent =
      `${record.voice} · ${record.audio_seconds}s · ${when}` +
      (record.audio_available ? "" : " · audio missing");

    item.append(text, score, sub);
    if (record.audio_available) {
      const play = () => {
        $("result").hidden = false;
        showResult(record);
      };
      item.addEventListener("click", play);
      item.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); play(); }
      });
    }
    container.appendChild(item);
  }
}

/* ---------- enroll ---------- */

async function enroll(event) {
  event.preventDefault();
  const name = $("enroll-name").value.trim();
  const files = $("enroll-files").files;
  const status = $("enroll-status");
  const formData = new FormData();
  formData.append("name", name);
  for (const file of files) formData.append("files", file);

  $("enroll-btn").disabled = true;
  status.textContent = "processing recordings…";
  try {
    const info = await fetchJson("/api/voices", { method: "POST", body: formData });
    status.textContent =
      `enrolled '${info.name}' (${info.duration_seconds}s reference` +
      (info.has_holdout ? ", holdout reserved)" : ")");
    await refreshVoices(info.name);
    $("enroll-form").reset();
  } catch (error) {
    status.textContent = `error: ${error.message}`;
  } finally {
    $("enroll-btn").disabled = false;
  }
}

/* ---------- wiring ---------- */

function wireControls() {
  $("generate").addEventListener("click", generate);
  $("script").addEventListener("input", updateScriptStats);
  $("voice").addEventListener("change", updateVoiceHint);

  $("enroll-toggle").addEventListener("click", () => {
    const form = $("enroll-form");
    form.hidden = !form.hidden;
    $("enroll-toggle").setAttribute("aria-expanded", String(!form.hidden));
  });
  $("enroll-form").addEventListener("submit", enroll);

  $("script-file").addEventListener("change", async () => {
    const file = $("script-file").files[0];
    if (file) {
      $("script").value = await file.text();
      updateScriptStats();
    }
  });

  for (const id of ["exaggeration", "cfg", "temperature", "rate"]) {
    $(id).addEventListener("input", () => {
      $(`${id}-val`).textContent = parseFloat($(id).value).toFixed(2);
    });
  }
}

init();
