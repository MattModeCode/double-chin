/* Presentation helpers. Pure functions, no DOM. */
"use strict";

/** Rough planning figures used for the pre-flight estimate. */
const CHARS_PER_SPOKEN_SECOND = 15;
const SYNTHESIS_REALTIME_FACTOR = 0.2;

export function estimateAudioSeconds(text) {
  return text.length / CHARS_PER_SPOKEN_SECOND;
}

export function estimateWallSeconds(text) {
  return estimateAudioSeconds(text) / SYNTHESIS_REALTIME_FACTOR;
}

/** "8s" / "3 min" — coarse on purpose, these are estimates. */
export function formatDuration(totalSeconds) {
  const seconds = Math.max(0, Math.round(totalSeconds));
  if (seconds < 90) return `${seconds}s`;
  return `${Math.round(seconds / 60)} min`;
}

/** "0:42" — for elapsed time, where the seconds matter. */
export function formatClock(totalSeconds) {
  const seconds = Math.max(0, Math.round(totalSeconds));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/** "1 chunk" / "3 chunks" — the noun agrees with the number. */
export function pluralize(count, singular, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}

export function formatCount(value) {
  return value.toLocaleString();
}

export function formatWhen(iso) {
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "";
  const today = new Date();
  const sameDay =
    when.getFullYear() === today.getFullYear() &&
    when.getMonth() === today.getMonth() &&
    when.getDate() === today.getDate();
  return sameDay
    ? when.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
    : when.toLocaleDateString([], { month: "short", day: "numeric" });
}

/** Maps the backend's verdict string onto a colour tone. */
export function verdictTone(verdict) {
  if (!verdict) return "plain";
  if (verdict.includes("strong") || verdict === "match") return "ok";
  if (verdict === "borderline") return "warn";
  return "err";
}
