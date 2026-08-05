#!/usr/bin/env bash
set -euo pipefail

AGENTS_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
CONFIG_FILE="${OLLAMA_CONFIG_FILE:-$(cd -- "$AGENTS_DIR/.." && pwd)/config/ollama.json}"
COMPRESS_SCRIPT="$AGENTS_DIR/headroom_compress.py"
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

# Loads the prior conversation (a JSON array of {role, content} messages) from
# a session file, if one was given and already exists. Empty/missing means a
# fresh conversation.
load_history() {
  local session_file="$1"
  if [[ -n "$session_file" && -f "$session_file" ]]; then
    jq -c '.' "$session_file" 2>/dev/null || echo '[]'
  else
    echo '[]'
  fi
}

save_history() {
  local session_file="$1"
  local history_json="$2"
  if [[ -n "$session_file" ]]; then
    mkdir -p "$(dirname -- "$session_file")"
    printf '%s' "$history_json" > "$session_file"
  fi
}

# Compresses a JSON messages array with Headroom right before it goes out to
# Ollama. Never touches what's stored in the session file -- compression is
# wire-only, same as the frontier agent.
compress_messages() {
  local messages_json="$1"
  local model_name="$2"
  python3 "$COMPRESS_SCRIPT" "$model_name" <<<"$messages_json"
}

call_ollama() {
  local prompt="$1"
  local session_file="${2:-}"
  log_entry "PROMPT" "ollama" "$prompt"

  local model_name="${MODEL:-${OLLAMA_MODEL:-llama3.2:3b}}"
  local host_name="$HOST"

  local history
  history=$(load_history "$session_file")

  # Append the new user turn to whatever conversation already exists, so the
  # model sees the old messages plus the new one instead of just the new one.
  local messages
  messages=$(jq -c --arg content "$prompt" '. + [{"role": "user", "content": $content}]' <<<"$history")

  local compressed_messages
  compressed_messages=$(compress_messages "$messages" "$model_name")
  log_entry "PROMPT_COMPRESSED" "ollama" "$(jq -r '.[-1].content' <<<"$compressed_messages")"

  local body
  body=$(jq -nc --argjson messages "$compressed_messages" --arg model "$model_name" '{model: $model, messages: $messages, stream: false}')
  local response
  response=$(curl -sS -X POST "$host_name/api/chat" -H 'Content-Type: application/json' -d "$body")

  if ! jq -e '.message.content' >/dev/null 2>&1 <<<"$response"; then
    echo "Unable to reach Ollama at $host_name. Make sure Ollama is running and the model '$model_name' is available." >&2
    exit 1
  fi

  local text
  text=$(jq -r '.message.content' <<<"$response")
  log_entry "OUTPUT" "ollama" "$text"

  # Persist both the new user turn and the assistant reply, so the next call
  # with this session file appends to the full history rather than replacing it.
  local updated_history
  updated_history=$(jq -c --arg content "$text" '. + [{"role": "assistant", "content": $content}]' <<<"$messages")
  save_history "$session_file" "$updated_history"

  printf '%s' "$text"
}

if [[ $# -eq 0 ]]; then
  echo "Usage: ./ollama_agent.sh \"prompt\" [session_file]" >&2
  exit 1
fi

load_config
call_ollama "$1" "${2:-}"
