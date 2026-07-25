#!/usr/bin/env bash
set -euo pipefail

CONFIG_FILE="${OLLAMA_CONFIG_FILE:-$(cd -- "$(dirname -- "$0")"/.. && pwd)/config/ollama.json}"
MODEL="${OLLAMA_MODEL:-}"
HOST="${OLLAMA_HOST:-http://localhost:11434}"

load_config() {
  if [[ -f "$CONFIG_FILE" ]]; then
    MODEL=$(jq -r '.model // empty' "$CONFIG_FILE")
    HOST=$(jq -r '.host // env.OLLAMA_HOST // "http://localhost:11434"' "$CONFIG_FILE")
  fi
}

call_ollama() {
  local prompt="$1"
  log_entry "PROMPT" "ollama" "$prompt"
  local model_name="${MODEL:-${OLLAMA_MODEL:-llama3.2:3b}}"
  local host_name="$HOST"
  local body
  body=$(jq -nc --arg prompt "$prompt" --arg model "$model_name" '{model: $model, prompt: $prompt, stream: false}')
  local response
  response=$(curl -sS -X POST "$host_name/api/generate" -H 'Content-Type: application/json' -d "$body")

  if ! jq -e '.response' >/dev/null 2>&1 <<<"$response"; then
    echo "Unable to reach Ollama at $host_name. Make sure Ollama is running and the model '$model_name' is available." >&2
    exit 1
  fi

  local text
  text=$(jq -r '.response' <<<"$response")
  log_entry "OUTPUT" "ollama" "$text"
  printf '%s' "$text"
}

if [[ $# -eq 0 ]]; then
  echo "Usage: ./ollama_agent.sh \"prompt\"" >&2
  exit 1
fi

load_config
call_ollama "$1"
