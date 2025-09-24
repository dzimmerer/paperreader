const json = async (url, opts = {}) => {
  const r = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
};

export async function createSession(url) {
  return json("/api/session", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export async function getState(sessionId) {
  return json(`/api/session/${sessionId}/state`);
}

export async function control(sessionId, action) {
  return json(`/api/session/${sessionId}/control`, {
    method: "POST",
    body: JSON.stringify({ action }),
  });
}

export async function fetchAudioBlob(sessionId, divIdx, sentenceIdx) {
  const r = await fetch(
    `/api/session/${sessionId}/audio?div_idx=${divIdx}&sentence_idx=${sentenceIdx}`
  );
  if (!r.ok) throw new Error("Audio not ready");
  return r.blob();
}
