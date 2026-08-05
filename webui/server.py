#!/usr/bin/env python3
"""
Local, dev-only web UI for manually testing prompt_optimizer.sh.

Not part of the shipped CLI product (see the "Out of Scope" section of
REQUIREMENTS.md) -- this just drives the existing script as a subprocess
and streams its stdout/stderr to a browser so a clarifying-question
back-and-forth can be exercised without a terminal.

Usage:
    python3 webui/server.py [--port 8765]

Then open http://127.0.0.1:8765/
"""
import argparse
import json
import mimetypes
import os
import queue
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "prompt_optimizer.sh"
STATIC_DIR = Path(__file__).resolve().parent / "static"

SESSION_NAME_RE = __import__("re").compile(r"^[A-Za-z0-9._-]+$")


class Run:
    def __init__(self, process: subprocess.Popen):
        self.process = process
        self.events: "queue.Queue[dict]" = queue.Queue()
        self.lock = threading.Lock()
        self.exited = False


RUNS: dict[str, Run] = {}
RUNS_LOCK = threading.Lock()


def _pump(stream, run: Run, stream_type: str) -> None:
    for line in iter(stream.readline, ""):
        run.events.put({"type": stream_type, "line": line.rstrip("\n")})
    stream.close()


def _wait_and_finalize(run: Run, stdout_thread: threading.Thread, stderr_thread: threading.Thread) -> None:
    stdout_thread.join()
    stderr_thread.join()
    code = run.process.wait()
    run.exited = True
    run.events.put({"type": "exit", "code": code})


def start_run(params: dict) -> str:
    prompt = (params.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required")
    if prompt.startswith("-"):
        # prompt_optimizer.sh's arg parser has no positional-args separator,
        # so a leading "-" would be swallowed as an (unknown/help) flag.
        raise ValueError("prompt may not start with '-'")

    session = (params.get("session") or "").strip() or "default"
    if not SESSION_NAME_RE.match(session):
        raise ValueError("session name may only contain letters, digits, '.', '_', '-'")

    args = ["bash", str(SCRIPT_PATH)]
    if params.get("model"):
        args += ["--model", params["model"]]
    if params.get("host"):
        args += ["--host", params["host"]]
    if params.get("output"):
        args += ["--output", params["output"]]
    if params.get("frontier_config"):
        args += ["--frontier-config", params["frontier_config"]]
    args += ["--session", session]
    if params.get("reset_session"):
        args += ["--reset-session"]
    # Note: prompt_optimizer.sh's arg parser treats "--" as "stop parsing and
    # discard the rest", not as a positional-args separator, so the prompt
    # must be appended as a plain trailing argument (as the CLI docs show).
    args.append(prompt)

    process = subprocess.Popen(
        args,
        cwd=str(REPO_ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    run = Run(process)
    stdout_thread = threading.Thread(target=_pump, args=(process.stdout, run, "stdout"), daemon=True)
    stderr_thread = threading.Thread(target=_pump, args=(process.stderr, run, "stderr"), daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    threading.Thread(target=_wait_and_finalize, args=(run, stdout_thread, stderr_thread), daemon=True).start()

    run_id = uuid.uuid4().hex
    with RUNS_LOCK:
        RUNS[run_id] = run
    return run_id


def send_input(run_id: str, text: str) -> None:
    with RUNS_LOCK:
        run = RUNS.get(run_id)
    if run is None:
        raise KeyError("unknown run id")
    with run.lock:
        if run.exited or run.process.stdin.closed:
            raise RuntimeError("process has already exited")
        run.process.stdin.write(text + "\n")
        run.process.stdin.flush()


class Handler(BaseHTTPRequestHandler):
    server_version = "PromptOptimizerWebUI/0.1"

    def log_message(self, fmt, *args):  # noqa: A002 - quiet default logging
        pass

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _serve_static(self, rel_path: str) -> None:
        if rel_path in ("", "/"):
            rel_path = "index.html"
        rel_path = rel_path.lstrip("/")
        file_path = (STATIC_DIR / rel_path).resolve()
        if STATIC_DIR not in file_path.parents and file_path != STATIC_DIR:
            self.send_error(404)
            return
        if not file_path.is_file():
            self.send_error(404)
            return
        content_type, _ = mimetypes.guess_type(str(file_path))
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802 - stdlib naming convention
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/run/") and path.endswith("/events"):
            run_id = path[len("/api/run/") : -len("/events")]
            self._handle_events(run_id)
            return

        self._serve_static(path)

    def do_POST(self):  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/run":
            try:
                params = self._read_json_body()
                run_id = start_run(params)
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            self._send_json(200, {"run_id": run_id})
            return

        if path.startswith("/api/run/") and path.endswith("/input"):
            run_id = path[len("/api/run/") : -len("/input")]
            try:
                body = self._read_json_body()
                send_input(run_id, body.get("text", ""))
            except KeyError:
                self._send_json(404, {"error": "unknown run id"})
                return
            except RuntimeError as exc:
                self._send_json(409, {"error": str(exc)})
                return
            self._send_json(200, {"ok": True})
            return

        self.send_error(404)

    def _handle_events(self, run_id: str) -> None:
        with RUNS_LOCK:
            run = RUNS.get(run_id)
        if run is None:
            self.send_error(404)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            while True:
                event = run.events.get()
                data = json.dumps(event)
                self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                self.wfile.flush()
                if event.get("type") == "exit":
                    break
        except (BrokenPipeError, ConnectionResetError):
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if not SCRIPT_PATH.is_file():
        raise SystemExit(f"Cannot find prompt_optimizer.sh at {SCRIPT_PATH}")

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Prompt Optimizer test UI running at http://127.0.0.1:{args.port}/")
    print("Local only -- this drives real Ollama/frontier LLM calls, same as the CLI.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
