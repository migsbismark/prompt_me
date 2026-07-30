#!/usr/bin/env python3
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from headroom_util import compress_messages


def load_env_file(path: str) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_history(session_file: str) -> list:
    if not session_file:
        return []
    path = Path(session_file)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_history(session_file: str, messages: list) -> None:
    if not session_file:
        return
    path = Path(session_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(messages, handle)


def append_log(log_file: str, source: str, content: str) -> None:
    if not log_file:
        return
    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_content = str(content).replace("\n", "\\n")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [OUTPUT] [{source}] {safe_content}\n")


def _as_messages(prompt_or_messages) -> list:
    """Accepts either a plain prompt string (single-turn) or a list of
    {role, content} messages (full conversation), and always returns a
    messages list, so callers appending history don't need a special case."""
    if isinstance(prompt_or_messages, str):
        return [{"role": "user", "content": prompt_or_messages}]
    return prompt_or_messages


def _to_gemini_contents(messages: list) -> list:
    return [
        {
            "role": "model" if message["role"] == "assistant" else "user",
            "parts": [{"text": message["content"]}],
        }
        for message in messages
    ]


def build_request(config: dict, prompt_or_messages, api_key: str):
    provider = config.get("provider", "openai")
    messages = _as_messages(prompt_or_messages)

    if provider == "openai":
        payload = json.dumps({
            "model": config.get("model", "gpt-4.1-mini"),
            "messages": messages,
        }).encode("utf-8")
        return urllib.request.Request(
            f"{config.get('api_base', 'https://api.openai.com/v1')}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

    if provider == "anthropic":
        payload = json.dumps({
            "model": config.get("model", "claude-3-5-sonnet-latest"),
            "max_tokens": config.get("max_tokens", 1024),
            "messages": messages,
        }).encode("utf-8")
        return urllib.request.Request(
            f"{config.get('api_base', 'https://api.anthropic.com/v1')}/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": config.get("anthropic_version", "2023-06-01"),
            },
            method="POST",
        )

    if provider == "azure_openai":
        deployment = config.get("deployment", "gpt-4o")
        api_version = config.get("api_version", "2024-02-01")
        payload = json.dumps({
            "messages": messages,
        }).encode("utf-8")
        url = f"{config.get('api_base', 'https://example.openai.azure.com')}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
        return urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "api-key": api_key,
            },
            method="POST",
        )

    if provider == "gemini":
        model = config.get("model", "gemini-2.0-flash")
        api_key = config.get("api_key", api_key)
        url = f"{config.get('api_base', 'https://generativelanguage.googleapis.com/v1beta')}/models/{model}:generateContent?key={api_key}"
        payload = json.dumps({
            "contents": _to_gemini_contents(messages),
        }).encode("utf-8")
        return urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

    if provider == "openai_compatible":
        payload = json.dumps({
            "model": config.get("model", "local-model"),
            "messages": messages,
        }).encode("utf-8")
        return urllib.request.Request(
            f"{config.get('api_base', 'http://localhost:8080/v1')}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

    raise ValueError(f"Unsupported provider: {provider}")


def parse_response(provider: str, body: dict):
    if provider == "anthropic":
        return body["content"][0]["text"]
    if provider in {"openai", "azure_openai", "openai_compatible"}:
        return body["choices"][0]["message"]["content"]
    if provider == "gemini":
        return body["candidates"][0]["content"]["parts"][0]["text"]
    raise ValueError(f"Unsupported provider: {provider}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: ./frontier_llm_agent.py \"prompt\" [config_path] [session_file]", file=sys.stderr)
        sys.exit(1)

    config_path = Path(sys.argv[2]).resolve() if len(sys.argv) >= 3 else (Path(__file__).resolve().parent.parent / "config" / "frontier_llm.json")
    config = load_config(str(config_path))
    session_file = sys.argv[3] if len(sys.argv) >= 4 else ""

    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_env_file(str(env_path))

    log_file = os.getenv("PROMPT_LOG_FILE")
    append_log(log_file, "frontier_prompt", sys.argv[1])

    prompt = sys.argv[1]
    provider = config.get("provider", "openai")

    # Append the new user turn to whatever conversation is already on disk, so
    # the frontier model sees the old messages plus the new one.
    history = load_history(session_file)
    messages = history + [{"role": "user", "content": prompt}]

    messages_to_send = compress_messages(messages, config.get("model"))
    append_log(log_file, "frontier_prompt_compressed", messages_to_send[-1]["content"])

    api_key = os.getenv(config.get("api_key_env", "OPENAI_API_KEY"))
    if not api_key and provider not in {"gemini"}:
        print(f"Missing API key from environment variable {config.get('api_key_env', 'OPENAI_API_KEY')}", file=sys.stderr)
        sys.exit(1)

    req = build_request(config, messages_to_send, api_key or "")
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8"), file=sys.stderr)
        sys.exit(1)

    response = parse_response(provider, body)
    append_log(log_file, "frontier_output", response)

    # Persist the uncompressed history (new user turn + assistant reply) so the
    # next call with this session file keeps appending to the full record;
    # compression only ever applies to what's sent over the wire.
    save_history(session_file, messages + [{"role": "assistant", "content": response}])

    print(response)


if __name__ == "__main__":
    main()
