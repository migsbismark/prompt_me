# Test UI (dev tool, not a product feature)

A small local web page for manually exercising [`prompt_optimizer.sh`](../prompt_optimizer.sh) --
mainly the clarifying-question back-and-forth, which is awkward to test from a
plain terminal. This is **not** a supported interface for the application;
REQUIREMENTS.md explicitly keeps the app CLI-only. This tool just spawns the
same CLI script as a subprocess and streams its output to a browser.

Same prerequisites as the CLI: Ollama reachable, `.env` populated, and
`config/frontier_llm.json` pointing at a valid provider -- this makes the same
real network calls the CLI would.

No extra dependencies (stdlib only).

## Run it

```bash
python3 webui/server.py            # http://127.0.0.1:8765
python3 webui/server.py --port 9000
```

Fill in the prompt (and optionally model/host/session/config overrides), hit
Run, and watch the log stream in. Whenever the script asks a clarifying
question, an answer box appears -- type a reply and send it, same as typing
into the terminal prompt.

## How it works

`webui/server.py` runs `prompt_optimizer.sh` as a subprocess with piped
stdin/stdout/stderr. stdout/stderr lines are pushed to the browser over
Server-Sent Events (`/api/run/<id>/events`); answers typed in the browser are
written to the subprocess's stdin (`/api/run/<id>/input`). The server binds to
`127.0.0.1` only.
