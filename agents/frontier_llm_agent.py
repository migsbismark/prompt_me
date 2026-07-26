#!/usr/bin/env python3
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from headroom import compress


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


def append_log(log_file: str, source: str, content: str) -> None:
    if not log_file:
        return
    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_content = str(content).replace("\n", "\\n")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [OUTPUT] [{source}] {safe_content}\n")


def build_request(config: dict, prompt: str, api_key: str):
    provider = config.get("provider", "openai")
    if provider == "openai":
        payload = json.dumps({
            "model": config.get("model", "gpt-4.1-mini"),
            "messages": [{"role": "user", "content": prompt}],
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
            "messages": [{"role": "user", "content": prompt}],
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
            "messages": [{"role": "user", "content": prompt}],
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
            "contents": [{"parts": [{"text": prompt}]}],
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
            "messages": [{"role": "user", "content": prompt}],
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
        print("Usage: ./frontier_llm_agent.py \"prompt\" [config_path]", file=sys.stderr)
        sys.exit(1)

    config_path = Path(sys.argv[2]).resolve() if len(sys.argv) >= 3 else (Path(__file__).resolve().parent.parent / "config" / "frontier_llm.json")
    config = load_config(str(config_path))

    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_env_file(str(env_path))

    log_file = os.getenv("PROMPT_LOG_FILE")
    append_log(log_file, "frontier_prompt", sys.argv[1])

    prompt = sys.argv[1]
    provider = config.get("provider", "openai")

    compressed_messages = compress([{"role": "user", "content": prompt}], model=config.get("model"))
    prompt = compressed_messages[-1]["content"]
    append_log(log_file, "frontier_prompt_compressed", prompt)

    api_key = os.getenv(config.get("api_key_env", "OPENAI_API_KEY"))
    if not api_key and provider not in {"gemini"}:
        print(f"Missing API key from environment variable {config.get('api_key_env', 'OPENAI_API_KEY')}", file=sys.stderr)
        sys.exit(1)

    req = build_request(config, prompt, api_key or "")
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8"), file=sys.stderr)
        sys.exit(1)

    response = parse_response(provider, body)
    append_log(log_file, "frontier_output", response)
    print(response)


if __name__ == "__main__":
    main()
