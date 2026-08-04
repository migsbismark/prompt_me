# Prompt Optimizer — Requirements Document

## 1. Purpose

Prompt Optimizer is a CLI workflow that uses a local Ollama model to evaluate and improve a user's prompt before forwarding it to a configurable frontier LLM, in order to get better results without the user manually rewriting every prompt.

## 2. Scope

Covers the CLI entry point ([prompt_optimizer.sh](prompt_optimizer.sh)), the local model agent ([agents/ollama_agent.sh](agents/ollama_agent.sh)), and the frontier model agent ([agents/frontier_llm_agent.py](agents/frontier_llm_agent.py)), including their shared conversation-history and compression behavior.

## 3. Functional Requirements

### 3.1 Prompt clarity evaluation
- FR-1: The system shall submit the user's initial prompt to the local Ollama model and classify it as `CLEAR` or `NEEDS_ENHANCEMENT`.
- FR-2: If classified `CLEAR`, the system shall return the original prompt unchanged, optionally write it to an output file, and shall **not** call the frontier model.

### 3.2 Clarifying questions
- FR-3: If the prompt needs enhancement, the system shall ask the user up to 5 clarifying questions, one at a time.
- FR-4: Before each question, the local model shall decide whether enough information has already been gathered (`DONE`) or whether another question is needed (`CONTINUE` + `Q:` line); the loop shall stop as soon as `DONE` is signaled, without waiting to exhaust the max question count.
- FR-5: If the local model's reply doesn't match the expected `DONE` / `CONTINUE, Q:` format twice in a row, the system shall stop asking further questions and proceed with whatever clarifications were already gathered, rather than looping indefinitely.

### 3.3 Prompt enhancement and accuracy guardrails
- FR-6: The system shall rewrite the original prompt using the local model, incorporating the user's answers, while instructing the model not to invent facts, names, numbers, dates, or other details not explicitly provided.
- FR-7: The system shall append an explicit accuracy-constraints block to the final prompt (rely only on given information; call out missing/ambiguous details; distinguish assumptions from stated facts) before it is sent to the frontier model.

### 3.4 Frontier model dispatch
- FR-8: The system shall send the final, guardrailed prompt to a configurable frontier LLM and print/log the response.
- FR-9: The system shall support the following frontier providers, selected via configuration: `openai`, `anthropic`, `azure_openai`, `gemini`, `openai_compatible`.
- FR-10: Provider selection, model, API base URL, and other provider-specific settings shall be read from [config/frontier_llm.json](config/frontier_llm.json) (overridable via `--frontier-config`).
- FR-11: API keys shall be read from environment variables (populated from a local `.env` file) named per the config's `api_key_env` field; the system shall fail with a clear error if a required key is missing (Gemini excluded, per its config-based key option).

### 3.5 Conversation history / sessions
- FR-12: The system shall maintain a persistent, growing message history (list of `{role, content}` messages) per model, stored on disk under `sessions/`, separately for the local model (`sessions/<name>_ollama.json`) and the frontier model (`sessions/<name>_frontier.json`).
- FR-13: Every prompt sent to a model shall be appended to that model's existing history (not sent in isolation), and every reply from that model shall be appended immediately after it.
- FR-14: Conversations shall be addressable by a session name (`--session NAME`, default `"default"`), so that re-running the CLI with the same session name continues the prior conversation instead of starting over.
- FR-15: The system shall support explicitly clearing a session's history before a run (`--reset-session`).
- FR-16: Session names shall be restricted to a safe character set (letters, digits, `.`, `_`, `-`) to prevent path-traversal via the session-file path.

### 3.6 Token-usage compression
- FR-17: Immediately before any request is sent over the network — to the local Ollama model or the frontier model — the full message history for that request shall be compressed using Headroom (`compress()`), to reduce token usage / cost and keep the conversation within the model's context budget.
- FR-18: Compression shall be wire-only: the history persisted to a session file shall always remain the original, uncompressed messages.

### 3.7 Configuration
- FR-19: Local Ollama model and host shall be configurable via [config/ollama.json](config/ollama.json), environment variables (`OLLAMA_MODEL`, `OLLAMA_HOST`), and/or CLI flags (`--model`, `--host`), with CLI/env taking precedence over the config file.
- FR-20: The system shall support overriding the final-prompt output destination via `--output FILE`.

### 3.8 Logging
- FR-21: Each run shall write a timestamped session log file under `logs/` (overridable via `--log-file` / `PROMPT_LOG_FILE`), unless otherwise specified.
- FR-22: The log file shall include a header with creation time, hostname, IP address, current user, working directory, selected Ollama model, frontier config path, and active session name/paths.
- FR-23: The log shall record every prompt and output exchanged with the local model (clarity check, each clarifying question, enhancement) and the frontier model, including the compressed version actually sent over the wire.

## 4. Non-Functional Requirements

- NFR-1: Secrets (API keys, `.env`) shall be excluded from version control via `.gitignore`; session history and logs (which may contain user content) shall likewise be excluded.
- NFR-2: The local-model call path shall degrade gracefully with a clear error message if Ollama is unreachable or the configured model is unavailable, rather than failing silently.
- NFR-3: The frontier-model call path shall surface HTTP errors (status + body) to stderr and exit non-zero rather than crashing with an unhandled exception.

## 5. Dependencies / Environment

- Ollama installed and running locally (or reachable via configured host), with at least one model pulled (e.g. `llama3.2:3b`).
- `curl`, `jq`, and Python 3 available on the host.
- Python dependency: [`headroom-ai`](https://github.com/headroomlabs-ai/headroom) (see [requirements.txt](requirements.txt)), used by both agents for compression.

## 6. Out of Scope

- Streaming responses (both agents currently request non-streaming completions).
- Multi-user or concurrent-session isolation beyond the `--session` name mechanism.
- A GUI or web interface; this is a CLI-only tool.
