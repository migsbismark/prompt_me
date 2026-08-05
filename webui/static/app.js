const runForm = document.getElementById("run-form");
const startBtn = document.getElementById("start-btn");
const statusEl = document.getElementById("status");
const logEl = document.getElementById("log");
const answerForm = document.getElementById("answer-form");
const answerInput = document.getElementById("answer");

let currentRunId = null;
let eventSource = null;

const QUESTION_RE = /^\d+\)\s/;

function appendLine(text, cls) {
  const div = document.createElement("div");
  div.className = "line" + (cls ? " " + cls : "");
  div.textContent = text;
  logEl.appendChild(div);
  logEl.scrollTop = logEl.scrollHeight;
}

function setRunning(running) {
  startBtn.disabled = running;
  statusEl.textContent = running ? "Running..." : "";
}

function fieldValue(id) {
  return document.getElementById(id).value.trim();
}

runForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  logEl.textContent = "";
  answerForm.classList.add("hidden");
  setRunning(true);

  const payload = {
    prompt: fieldValue("prompt"),
    model: fieldValue("model"),
    host: fieldValue("host"),
    session: fieldValue("session"),
    frontier_config: fieldValue("frontier_config"),
    output: fieldValue("output"),
    reset_session: document.getElementById("reset_session").checked,
  };

  let response;
  try {
    response = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    appendLine("Failed to reach the test UI server: " + err, "stderr");
    setRunning(false);
    return;
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    appendLine("Error: " + (body.error || response.statusText), "stderr");
    setRunning(false);
    return;
  }

  const body = await response.json();
  currentRunId = body.run_id;
  openStream(currentRunId);
});

function openStream(runId) {
  if (eventSource) {
    eventSource.close();
  }
  eventSource = new EventSource(`/api/run/${runId}/events`);

  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.type === "exit") {
      appendLine(`--- process exited (code ${data.code}) ---`, "exit");
      setRunning(false);
      answerForm.classList.add("hidden");
      eventSource.close();
      return;
    }

    if (!data.line) {
      return;
    }

    appendLine(data.line, data.type === "stderr" ? "stderr" : null);

    if (data.type === "stdout" && QUESTION_RE.test(data.line)) {
      answerForm.classList.remove("hidden");
      answerInput.value = "";
      answerInput.focus();
    }
  };

  eventSource.onerror = () => {
    appendLine("--- connection to test UI server lost ---", "stderr");
    setRunning(false);
  };
}

answerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!currentRunId) return;

  const text = answerInput.value;
  appendLine("> " + text, "local");
  answerForm.classList.add("hidden");

  try {
    const response = await fetch(`/api/run/${currentRunId}/input`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      appendLine("Error sending answer: " + (body.error || response.statusText), "stderr");
    }
  } catch (err) {
    appendLine("Failed to send answer: " + err, "stderr");
  }
});
