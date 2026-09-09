/* Double Chin — single-voice studio.
 *
 * The app is built around one enrolled voice: it is resolved once at boot and
 * never appears as a choice on the main surface. Voice management, enrolment
 * and environment facts all live in the Settings sheet.
 */
"use strict";

import { api } from "./api.js";
import {
  estimateAudioSeconds,
  estimateWallSeconds,
  formatClock,
  formatCount,
  formatDuration,
  formatWhen,
  pluralize,
  verdictTone,
} from "./format.js";

const DELIVERY_DEFAULTS = Object.freeze({
  exaggeration: 0.5,
  cfg: 0.5,
  temperature: 0.8,
  rate: 1,
});

const KNOB_LABELS = Object.freeze({
  exaggeration: "Expression",
  cfg: "Adherence",
  temperature: "Variation",
  rate: "Rate",
});

/* Which enrolled voice is "yours". Only ever set from the Settings sheet —
 * the composing surface never asks. */
const VOICE_KEY = "double-chin.voice";

const $ = (id) => document.getElementById(id);

function readStoredVoice() {
  try {
    return localStorage.getItem(VOICE_KEY);
  } catch (_) {
    return null;  // private window, or site data blocked
  }
}

function storeVoice(name) {
  try {
    localStorage.setItem(VOICE_KEY, name);
  } catch (_) { /* the choice simply does not persist */ }
}

const state = {
  voice: null,
  jobRunning: false,
  eventSource: null,
  timerHandle: null,
  jobStartedAt: null,
};

/* ---------- boot ---------- */

async function init() {
  wireControls();
  syncDelivery();
  updateScriptStats();
  await Promise.allSettled([refreshVoice(), refreshEnvironment(), refreshHistory()]);
}

/* ---------- voice ---------- */

async function refreshVoice(preferName) {
  let voices = [];
  try {
    voices = await api.listVoices();
  } catch (_) { /* leave the app in its no-voice state */ }

  const wanted = preferName ?? readStoredVoice();
  state.voice = voices.find((voice) => voice.name === wanted) ?? voices[0] ?? null;
  if (state.voice) storeVoice(state.voice.name);

  $("toolbar-voice").textContent = state.voice ? state.voice.name : "No voice";
  renderVoicePicker(voices);
  renderVoiceCard();
  renderIdle();
  updateGenerateEnabled();
}

/** Shown only when more than one voice is enrolled; the main surface never has it. */
function renderVoicePicker(voices) {
  const wrapper = $("voice-switch");
  const select = $("voice-select");
  wrapper.hidden = voices.length < 2;
  if (wrapper.hidden) return;

  select.textContent = "";
  for (const voice of voices) {
    const option = el("option", { value: voice.name, text: voice.name });
    if (voice.name === state.voice?.name) option.selected = true;
    select.append(option);
  }
}

function renderVoiceCard() {
  const card = $("voice-card");
  const hint = $("voice-hint");
  card.textContent = "";

  if (!state.voice) {
    card.append(el("div", { class: "voice-name", text: "No voice yet" }));
    hint.textContent =
      "Enrol a voice below from a few of your own recordings, then close this sheet.";
    return;
  }

  const name = el("div", { class: "voice-name", text: state.voice.name });
  const meta = el("div", {
    class: "voice-meta numeric",
    text: `${formatDuration(state.voice.duration_seconds)} reference`,
  });
  card.append(name, meta);

  hint.textContent = state.voice.has_holdout
    ? "Takes are checked against a held-out clip the model never conditions on."
    : "No held-out clip, so takes are checked against the reference itself.";
}

function renderIdle() {
  const idle = $("idle-state");
  idle.textContent = "";
  if (!state.voice) {
    idle.append(
      document.createTextNode("No voice is enrolled yet. "),
      el("button", { class: "link", type: "button", text: "Add one in Settings", id: "idle-settings" }),
      document.createTextNode("."),
    );
    $("idle-settings").addEventListener("click", openSettings);
    return;
  }
  idle.textContent =
    "The first take loads the model, which takes about ten seconds. After that it " +
    "synthesizes at roughly a fifth of realtime, a chunk at a time.";
}

/* ---------- environment ---------- */

async function refreshEnvironment() {
  let doctor;
  try {
    doctor = await api.doctor();
  } catch (_) {
    $("engine-pill").textContent = "";
    return;
  }

  const device = doctor.device ? doctor.device.toUpperCase() : "no torch";
  $("engine-pill").textContent = "";
  $("engine-pill").append(
    el("b", { text: device }),
    document.createTextNode(doctor.weights_cached ? " · ready" : " · first run downloads weights"),
  );
  $("version").textContent = `v${doctor.version}`;

  const facts = $("env-facts");
  facts.textContent = "";
  const rows = [
    ["Device", device],
    ["PyTorch", doctor.torch ?? "not installed"],
    ["Model weights", doctor.weights_cached ? "cached" : "download on first take"],
    ["Voices", String(doctor.voices)],
    ["Home", doctor.double_chin_home],
  ];
  for (const [term, value] of rows) {
    facts.append(el("dt", { text: term }), el("dd", { text: value }));
  }
}

/* ---------- script ---------- */

function updateScriptStats() {
  const text = $("script").value;
  const chars = text.length;

  $("script-stats").textContent = chars === 0
    ? ""
    : `${formatCount(chars)} characters · about ${formatDuration(estimateAudioSeconds(text))} of audio`;

  $("eta").textContent = chars === 0
    ? ""
    : `Roughly ${formatDuration(estimateWallSeconds(text))} to synthesize`;

  updateGenerateEnabled();
}

function updateGenerateEnabled() {
  $("generate").disabled =
    state.jobRunning || state.voice === null || $("script").value.trim() === "";
}

/* ---------- delivery ---------- */

function setRangeFill(input) {
  const min = parseFloat(input.min);
  const max = parseFloat(input.max);
  const ratio = (parseFloat(input.value) - min) / (max - min);
  input.style.setProperty("--fill", `${(ratio * 100).toFixed(2)}%`);
}

function knobValue(id) {
  return parseFloat($(id).value);
}

/** Keeps the range fills, the numeric outputs, and the collapsed summary in step. */
function syncDelivery() {
  const changed = [];
  for (const [id, fallback] of Object.entries(DELIVERY_DEFAULTS)) {
    const input = $(id);
    setRangeFill(input);
    const value = knobValue(id);
    const suffix = id === "rate" ? "×" : "";
    $(`${id}-val`).textContent = `${value.toFixed(2)}${suffix}`;
    if (Math.abs(value - fallback) > 1e-9) {
      changed.push(`${KNOB_LABELS[id]} ${value.toFixed(2)}${suffix}`);
    }
  }
  if ($("seed").value.trim() !== "") changed.push("fixed seed");

  $("delivery-summary").textContent = changed.length === 0 ? "Default" : changed.join(" · ");
}

function resetDelivery() {
  for (const [id, fallback] of Object.entries(DELIVERY_DEFAULTS)) {
    $(id).value = String(fallback);
  }
  $("seed").value = "";
  syncDelivery();
}

/* ---------- generate ---------- */

async function generate() {
  if ($("generate").disabled) return;

  const seedRaw = $("seed").value.trim();
  const payload = {
    voice: state.voice.name,
    text: $("script").value,
    exaggeration: knobValue("exaggeration"),
    cfg_weight: knobValue("cfg"),
    temperature: knobValue("temperature"),
    rate: knobValue("rate"),
    seed: seedRaw === "" ? null : parseInt(seedRaw, 10),
  };

  let job;
  try {
    job = await api.createJob(payload);
  } catch (error) {
    resetJobCard();
    setStatus("Failed", "error");
    showJobError(error.message);
    return;
  }

  beginJobUi();
  followJob(job.job_id);
}

/** Clears the job card of any previous run and brings it forward. */
function resetJobCard() {
  $("idle-state").hidden = true;
  $("result").hidden = true;
  $("job-state").hidden = false;
  $("job-error").hidden = true;
  $("chunk-list").textContent = "";
  $("job-timer").textContent = "";
  $("bar-fill").style.width = "0%";
}

function beginJobUi() {
  state.jobRunning = true;
  state.jobStartedAt = Date.now();
  updateGenerateEnabled();

  resetJobCard();
  $("bar-fill").style.width = "2%";
  setStatus("Loading the model…", "");

  state.timerHandle = setInterval(() => {
    $("job-timer").textContent = formatClock((Date.now() - state.jobStartedAt) / 1000);
  }, 1000);
}

function setStatus(text, tone) {
  const status = $("job-status");
  status.textContent = text;
  status.className = `status ${tone}`;
}

function followJob(jobId) {
  const source = api.jobEvents(jobId);
  state.eventSource = source;

  source.addEventListener("progress", (event) => {
    const data = JSON.parse(event.data);
    setStatus(`Synthesizing ${data.chunk} of ${data.total}`, "");
    renderChunk(data);
    $("bar-fill").style.width = `${((data.chunk - 0.5) / data.total) * 100}%`;
  });

  source.addEventListener("verifying", (event) => {
    const data = JSON.parse(event.data);
    markAllChunksDone();
    $("bar-fill").style.width = "96%";
    setStatus(`Checking the voice against ${data.against}…`, "");
  });

  source.addEventListener("done", (event) => {
    const record = JSON.parse(event.data);
    finishJob();
    setStatus("Done", "done");
    $("bar-fill").style.width = "100%";
    showResult(record);
    refreshHistory();
  });

  source.addEventListener("error", (event) => {
    // Fires both for server-sent error events (which carry data) and for
    // transport errors (which do not); a stream closed after "done" also
    // lands here, hence the jobRunning guard.
    if (event.data) {
      const data = JSON.parse(event.data);
      finishJob();
      setStatus("Failed", "error");
      showJobError(data.message);
    } else if (state.jobRunning) {
      finishJob();
      setStatus("Lost the connection", "error");
      showJobError(
        "The progress stream dropped. The take may still be running — check Recent in a moment.",
      );
    }
  });
}

function renderChunk(data) {
  markAllChunksDone();
  const item = el("li", { class: "active" });
  item.append(el("span", { class: "idx", text: `${data.chunk}/${data.total}` }));
  item.append(document.createTextNode(data.text));
  $("chunk-list").append(item);
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

function showResult(record) {
  $("idle-state").hidden = true;
  $("job-state").hidden = true;
  $("result").hidden = false;

  const chip = $("verdict-chip");
  if (record.similarity != null) {
    chip.textContent = `${record.verdict} · ${record.similarity.toFixed(3)}`;
    chip.className = `verdict ${verdictTone(record.verdict)}`;
  } else {
    chip.textContent = "Not verified";
    chip.className = "verdict plain";
  }

  $("result-meta").textContent =
    `${formatDuration(record.audio_seconds)} of audio · ${pluralize(record.chunk_count, "chunk")} · ` +
    `${formatDuration(record.wall_seconds)} on ${record.device}`;

  const player = $("player");
  player.src = api.audioUrl(record.id);
  $("download").href = api.audioUrl(record.id, true);
  player.play().catch(() => { /* autoplay may be blocked; the controls still work */ });
}

/* ---------- history ---------- */

async function refreshHistory() {
  let records;
  try {
    records = await api.listHistory();
  } catch (_) {
    return;
  }

  const container = $("history");
  container.textContent = "";

  if (records.length === 0) {
    container.append(el("p", { class: "history-empty", text: "Nothing generated yet." }));
    return;
  }

  for (const record of records) {
    container.append(historyRow(record));
  }
}

function historyRow(record) {
  const playable = record.audio_available;
  const item = el("div", {
    class: "history-item",
    role: "button",
    tabindex: playable ? "0" : "-1",
  });
  if (!playable) item.setAttribute("aria-disabled", "true");

  item.append(el("div", { class: "txt", text: record.text_preview }));

  const score = el("div", { class: "score" });
  if (record.similarity != null) {
    score.textContent = record.similarity.toFixed(3);
    score.classList.add(verdictTone(record.verdict));
  }
  item.append(score);

  const parts = [record.voice, formatDuration(record.audio_seconds), formatWhen(record.created)];
  if (!playable) parts.push("audio missing");
  item.append(el("div", { class: "sub", text: parts.filter(Boolean).join(" · ") }));

  if (playable) {
    const play = () => showResult(record);
    item.addEventListener("click", play);
    item.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        play();
      }
    });
  }
  return item;
}

/* ---------- settings ---------- */

function openSettings() {
  const sheet = $("settings");
  if (!sheet.open) sheet.showModal();
}

function closeSettings() {
  const sheet = $("settings");
  if (sheet.open) sheet.close();
}

async function enroll(event) {
  event.preventDefault();
  const status = $("enroll-status");
  const formData = new FormData();
  formData.append("name", $("enroll-name").value.trim());
  formData.append("overwrite", $("enroll-overwrite").checked ? "true" : "false");
  for (const file of $("enroll-files").files) formData.append("files", file);

  $("enroll-btn").disabled = true;
  status.textContent = "Processing the recordings…";
  try {
    const info = await api.enrollVoice(formData);
    status.textContent = info.has_holdout
      ? `Enrolled ${info.name} with a held-out clip reserved.`
      : `Enrolled ${info.name}.`;
    $("enroll-form").reset();
    await Promise.all([refreshVoice(info.name), refreshEnvironment()]);
  } catch (error) {
    status.textContent = error.status === 409
      ? `${error.message} Tick the replace box to overwrite it.`
      : error.message;
  } finally {
    $("enroll-btn").disabled = false;
  }
}

/* ---------- wiring ---------- */

function wireControls() {
  $("generate").addEventListener("click", generate);
  $("script").addEventListener("input", updateScriptStats);

  for (const id of Object.keys(DELIVERY_DEFAULTS)) {
    $(id).addEventListener("input", syncDelivery);
  }
  $("seed").addEventListener("input", syncDelivery);
  $("reset-delivery").addEventListener("click", resetDelivery);

  $("script-file").addEventListener("change", async () => {
    const file = $("script-file").files[0];
    if (!file) return;
    $("script").value = await file.text();
    $("script-file").value = "";
    updateScriptStats();
  });

  $("voice-select").addEventListener("change", (event) => {
    storeVoice(event.target.value);
    refreshVoice(event.target.value);
  });

  $("settings-open").addEventListener("click", openSettings);
  $("settings-close").addEventListener("click", closeSettings);
  $("enroll-form").addEventListener("submit", enroll);

  // Clicking the dimmed area outside the sheet dismisses it, as a sheet should.
  $("settings").addEventListener("click", (event) => {
    if (event.target === $("settings")) closeSettings();
  });

  document.addEventListener("keydown", (event) => {
    if (!(event.metaKey || event.ctrlKey) || event.key !== "Enter") return;
    if ($("settings").open) return;
    event.preventDefault();
    generate();
  });
}

/* ---------- tiny DOM helper ---------- */

function el(tag, options = {}) {
  const node = document.createElement(tag);
  const { text, ...attributes } = options;
  for (const [name, value] of Object.entries(attributes)) {
    node.setAttribute(name, value);
  }
  if (text !== undefined) node.textContent = text;
  return node;
}

init();
