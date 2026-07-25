#!/usr/bin/env bash
set -euo pipefail

MODEL="${OLLAMA_MODEL:-llama3.2:3b}"
HOST="${OLLAMA_HOST:-http://localhost:11434}"
OUTPUT_FILE=""
INITIAL_PROMPT=""
SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" && pwd)
OLLAMA_AGENT="$SCRIPT_DIR/agents/ollama_agent.sh"
FRONTIER_AGENT="$SCRIPT_DIR/agents/frontier_llm_agent.py"
CONFIG_FILE="$SCRIPT_DIR/config/frontier_llm.json"
LOG_FILE="${PROMPT_LOG_FILE:-}"

usage() {
  cat <<'EOF'
Usage: ./prompt_optimizer.sh [options] "Your prompt"

Options:
  --model MODEL      Ollama model to use (default: llama3.2:3b)
  --host URL         Ollama server URL (default: http://localhost:11434)
  --output FILE      Write the final prompt to a file
  --frontier-config FILE  Path to the frontier LLM config JSON (default: config/frontier_llm.json)
  --log-file FILE    Write timestamped prompt and agent logs to this file
  -h, --help         Show this help text
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model)
      [[ $# -ge 2 ]] || { echo "Missing value for --model" >&2; exit 1; }
      MODEL="$2"
      shift 2
      ;;
    --host)
      [[ $# -ge 2 ]] || { echo "Missing value for --host" >&2; exit 1; }
      HOST="$2"
      shift 2
      ;;
    --output)
      [[ $# -ge 2 ]] || { echo "Missing value for --output" >&2; exit 1; }
      OUTPUT_FILE="$2"
      shift 2
      ;;
    --frontier-config)
      [[ $# -ge 2 ]] || { echo "Missing value for --frontier-config" >&2; exit 1; }
      CONFIG_FILE="$2"
      shift 2
      ;;
    --log-file)
      [[ $# -ge 2 ]] || { echo "Missing value for --log-file" >&2; exit 1; }
      LOG_FILE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    *)
      if [[ -z "$INITIAL_PROMPT" ]]; then
        INITIAL_PROMPT="$1"
      else
        echo "Unexpected argument: $1" >&2
        usage >&2
        exit 1
      fi
      shift
      ;;
  esac
done

if [[ -z "$INITIAL_PROMPT" ]]; then
  read -r -p "Enter the initial prompt: " INITIAL_PROMPT
fi

if [[ -z "$INITIAL_PROMPT" ]]; then
  echo "A prompt is required." >&2
  exit 1
fi

if [[ ! -f "$OLLAMA_AGENT" ]]; then
  echo "Missing Ollama agent: $OLLAMA_AGENT" >&2
  exit 1
fi

if [[ ! -f "$FRONTIER_AGENT" ]]; then
  echo "Missing frontier LLM agent: $FRONTIER_AGENT" >&2
  exit 1
fi

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Missing frontier config file: $CONFIG_FILE" >&2
  exit 1
fi

session_tag=$(date '+%Y%m%d_%H%M%S')
if [[ -z "$LOG_FILE" ]]; then
  LOG_FILE="$SCRIPT_DIR/logs/prompt_optimizer_${session_tag}.log"
fi
mkdir -p "$(dirname "$LOG_FILE")"

timestamp() {
  date '+%Y-%m-%d %H:%M:%S'
}

sanitize_for_log() {
  sed ':a;N;$!ba;s/\n/\\n/g'
}

write_session_header() {
  local hostname
  hostname=$(hostname)
  local ip_address
  ip_address=$(hostname -I 2>/dev/null | awk '{print $1}')
  if [[ -z "$ip_address" ]]; then
    ip_address="unknown"
  fi
  {
    echo "============================================================"
    echo "Prompt Optimizer Session Log"
    echo "Created: $(timestamp)"
    echo "Hostname: $hostname"
    echo "IP Address: $ip_address"
    echo "User: $(whoami)"
    echo "Working Directory: $PWD"
    echo "Ollama Model: $MODEL"
    echo "Frontier Config: $CONFIG_FILE"
    echo "============================================================"
  } >> "$LOG_FILE"
}

log_entry() {
  local level="$1"
  local source="$2"
  local message="$3"
  local safe_message
  safe_message=$(printf '%s' "$message" | sanitize_for_log)
  printf '[%s] [%s] [%s] %s\n' "$(timestamp)" "$level" "$source" "$safe_message" >> "$LOG_FILE"
}

export PROMPT_LOG_FILE="$LOG_FILE"
write_session_header

call_ollama() {
  local prompt="$1"
  log_entry "PROMPT" "ollama" "$prompt"
  local response
  response=$(OLLAMA_MODEL="$MODEL" OLLAMA_HOST="$HOST" "$OLLAMA_AGENT" "$prompt")
  log_entry "OUTPUT" "ollama" "$response"
  printf '%s' "$response"
}

log_entry "PROMPT" "user" "$INITIAL_PROMPT"

clarity_prompt=$(cat <<EOF
You are a prompt quality assistant.
Determine whether the following prompt is clear, specific, and actionable enough for a frontier LLM.
Return only one of these two labels on the first line:
CLEAR
NEEDS_ENHANCEMENT
If you return NEEDS_ENHANCEMENT, add three concise clarifying questions on the next three lines using the format Q1:, Q2:, Q3:.
Prompt:
$INITIAL_PROMPT
EOF
)

log_entry "PROMPT" "ollama_clarity" "$clarity_prompt"
clarity_response=$(call_ollama "$clarity_prompt")
decision=$(printf '%s
' "$clarity_response" | head -n 1 | tr -d '\r')

if [[ "$decision" == "CLEAR" ]]; then
  log_entry "OUTPUT" "ollama_clarity" "$clarity_response"
  echo "The initial prompt is already clear. No enhancement is needed."
  echo "$INITIAL_PROMPT"
  if [[ -n "$OUTPUT_FILE" ]]; then
    printf '%s\n' "$INITIAL_PROMPT" > "$OUTPUT_FILE"
  fi
  exit 0
fi

mapfile -t questions < <(printf '%s
' "$clarity_response" | sed -n '2,4p' | sed 's/^[[:space:]]*//')

if [[ ${#questions[@]} -lt 3 ]]; then
  echo "The model did not return three questions. Please try again." >&2
  exit 1
fi

echo "The prompt is a bit vague. Please answer these three questions to improve it:"
printf '1) %s\n' "${questions[0]#Q1: }"
printf '2) %s\n' "${questions[1]#Q2: }"
printf '3) %s\n' "${questions[2]#Q3: }"

read -r -p "Answer 1: " answer1
read -r -p "Answer 2: " answer2
read -r -p "Answer 3: " answer3

enhancement_prompt=$(cat <<EOF
You are a prompt optimizer.
Rewrite the following prompt so it is clearer, more specific, and more actionable for a frontier LLM.
Preserve the user's original intent and return only the improved prompt.
Original prompt:
$INITIAL_PROMPT

Clarifications:
1. $answer1
2. $answer2
3. $answer3
EOF
)

log_entry "PROMPT" "ollama_enhancement" "$enhancement_prompt"
enhanced_prompt=$(call_ollama "$enhancement_prompt")
log_entry "OUTPUT" "ollama_enhancement" "$enhanced_prompt"

echo "Enhanced prompt:"
echo "$enhanced_prompt"

if [[ -n "$OUTPUT_FILE" ]]; then
  printf '%s\n' "$enhanced_prompt" > "$OUTPUT_FILE"
fi

if [[ -f "$FRONTIER_AGENT" ]]; then
  log_entry "PROMPT" "frontier" "$enhanced_prompt"
  echo ""
  echo "Sending the optimized prompt to the configured frontier LLM agent..."
  frontier_response=$(python3 "$FRONTIER_AGENT" "$enhanced_prompt" "$CONFIG_FILE")
  log_entry "OUTPUT" "frontier" "$frontier_response"
  echo "$frontier_response"
fi
