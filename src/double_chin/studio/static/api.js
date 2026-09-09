/* Thin wrapper over the Studio HTTP API. No endpoint shapes are invented
 * here — every path below already exists in studio/app.py. */
"use strict";

async function request(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch (_) { /* error body was not JSON; keep the status line */ }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

export const api = {
  listVoices: () => request("/api/voices"),
  enrollVoice: (formData) => request("/api/voices", { method: "POST", body: formData }),
  createJob: (payload) =>
    request("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  listHistory: () => request("/api/history"),
  doctor: () => request("/api/doctor"),
  jobEvents: (jobId) => new EventSource(`/api/jobs/${jobId}/events`),
  audioUrl: (jobId, download = false) =>
    `/api/audio/${jobId}${download ? "?download=true" : ""}`,
};
