#!/usr/bin/env bash
set -euo pipefail

CONFIG_FILE="${OLLAMA_CONFIG_FILE:-$(cd -- "$(dirname -- "$0")"/.. && pwd)/config/ollama.json}"
MODEL="${OLLAMA_MODEL:-}"
HOST="${OLLAMA_HOST:-http://ollama:11434}"

log_entry() {
  local level="$1"
  local source="$2"
  local message="$3"
  if [[ -n "${PROMPT_LOG_FILE:-}" ]]; then
    printf '[%s] [%s] [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$level" "$source" "$message" >> "$PROMPT_LOG_FILE"
  fi
}

sanitize_for_log() {
  cat
}

load_config() {
  local configured_model=""
  local configured_host=""

  if [[ -f "$CONFIG_FILE" ]]; then
    configured_model=$(jq -r '.model // empty' "$CONFIG_FILE")
    configured_host=$(jq -r '.host // empty' "$CONFIG_FILE")
  fi

  MODEL="${OLLAMA_MODEL:-$configured_model}"
  HOST="${OLLAMA_HOST:-${configured_host:-http://ollama:11434}}"
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
