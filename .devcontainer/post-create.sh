#!/usr/bin/env bash
set -euo pipefail

MODEL="${OLLAMA_MODEL:-llama3.2:3b}"
OLLAMA_BASE_URL="${OLLAMA_HOST:-http://ollama:11434}"

for _ in $(seq 1 60); do
  if curl -fsS "$OLLAMA_BASE_URL/api/tags" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

curl -fsS "$OLLAMA_BASE_URL/api/pull" \
  -H 'Content-Type: application/json' \
  -d "{\"name\":\"$MODEL\",\"stream\":false}" >/tmp/ollama-pull.json

if ! jq -e '.status == "success"' /tmp/ollama-pull.json >/dev/null 2>&1; then
  echo "Failed to pull Ollama model $MODEL:" >&2
  cat /tmp/ollama-pull.json >&2
  exit 1
fi

echo "Ollama model $MODEL is ready."
