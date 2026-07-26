#!/usr/bin/env bash
set -euo pipefail

MODEL="${OLLAMA_MODEL:-llama3.2:3b}"
DEFAULT_HOST="http://localhost:11434"
HOST="${OLLAMA_HOST:-$DEFAULT_HOST}"
OUTPUT_FILE=""
INITIAL_PROMPT=""
SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" && pwd)
OLLAMA_AGENT="$SCRIPT_DIR/agents/ollama_agent.sh"
FRONTIER_AGENT="$SCRIPT_DIR/agents/frontier_llm_agent.py"
CONFIG_FILE="$SCRIPT_DIR/config/frontier_llm.json"
LOG_FILE="${PROMPT_LOG_FILE:-}"

load_ollama_config() {
  local config_host
  if [[ -f "$SCRIPT_DIR/config/ollama.json" ]]; then
    config_host=$(jq -r '.host // empty' "$SCRIPT_DIR/config/ollama.json")
    if [[ -z "${OLLAMA_HOST:-}" && -n "$config_host" ]]; then
      HOST="$config_host"
    fi
  fi
}

load_ollama_config

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
Return only one of these two labels, and nothing else:
CLEAR
NEEDS_ENHANCEMENT
Prompt:
$INITIAL_PROMPT
EOF
)

log_entry "PROMPT" "ollama_clarity" "$clarity_prompt"
if ! clarity_response=$(call_ollama "$clarity_prompt"); then
  exit 1
fi
log_entry "OUTPUT" "ollama_clarity" "$clarity_response"
decision=$(printf '%s
' "$clarity_response" | head -n 1 | tr -d '\r')

if [[ "$decision" == "CLEAR" ]]; then
  echo "The initial prompt is already clear. No enhancement is needed."
  echo "$INITIAL_PROMPT"
  if [[ -n "$OUTPUT_FILE" ]]; then
    printf '%s\n' "$INITIAL_PROMPT" > "$OUTPUT_FILE"
  fi
  exit 0
fi

MAX_CLARIFYING_QUESTIONS=5
conversation=""
question_count=0

echo "The prompt is a bit vague. I'll ask a few questions (up to $MAX_CLARIFYING_QUESTIONS) to improve it -- I'll stop early once I have enough."

MAX_MALFORMED_ATTEMPTS=2

while (( question_count < MAX_CLARIFYING_QUESTIONS )); do
  base_next_question_prompt=$(cat <<EOF
You are a prompt quality assistant clarifying a vague prompt before it is rewritten for a frontier LLM.
Original prompt:
$INITIAL_PROMPT

Clarifications gathered so far (may be empty):
$conversation

Decide whether you now have enough information to rewrite the original prompt clearly, specifically, and actionably for a frontier LLM.
- If you have enough information, respond with exactly one line and nothing else:
DONE
- If you still need more information, respond with exactly two lines and nothing else:
CONTINUE
Q: <one concise clarifying question that would most improve the prompt, not already asked above>
EOF
)

  question_text=""
  is_done=false
  malformed=false

  for (( attempt=1; attempt<=MAX_MALFORMED_ATTEMPTS; attempt++ )); do
    next_question_prompt="$base_next_question_prompt"
    if (( attempt > 1 )); then
      next_question_prompt+=$'\n\nYour previous reply did not follow the required format. Reply with ONLY the word DONE, or ONLY "CONTINUE" followed by a line starting with "Q:". Do not add any other words or commentary.'
    fi

    log_entry "PROMPT" "ollama_next_question" "$next_question_prompt"
    if ! next_response=$(call_ollama "$next_question_prompt"); then
      exit 1
    fi
    log_entry "OUTPUT" "ollama_next_question" "$next_response"

    # A question line is the strongest signal, regardless of what the first line said.
    # `|| true` prevents set -e/pipefail from killing the script when there is no Q: line to match
    # (e.g. a correctly formatted DONE reply), which previously aborted the whole run silently.
    question_text=$(printf '%s\n' "$next_response" | grep -m1 -iE '^[[:space:]]*Q:' | sed -E 's/^[[:space:]]*[Qq]:[[:space:]]*//' || true)
    if [[ -n "$question_text" ]]; then
      malformed=false
      break
    fi

    first_line=$(printf '%s\n' "$next_response" | head -n 1 | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    if printf '%s' "$first_line" | grep -qiE '^done[.!]?$'; then
      is_done=true
      malformed=false
      break
    fi

    malformed=true
  done

  if $is_done; then
    break
  fi

  if $malformed; then
    # The model failed to follow the format twice in a row; stop asking rather than loop forever.
    echo "The clarifying model gave an unexpected response; continuing with the clarifications gathered so far." >&2
    break
  fi

  question_count=$((question_count + 1))
  printf '%d) %s\n' "$question_count" "$question_text"
  read -r -p "Answer $question_count: " answer_text

  conversation+="Q${question_count}: ${question_text}"$'\n'"A${question_count}: ${answer_text}"$'\n'
done

if [[ -z "$conversation" ]]; then
  conversation="(no clarifications were gathered)"
fi

enhancement_prompt=$(cat <<EOF
You are a prompt optimizer.
Rewrite the following prompt so it is clearer, more specific, and more actionable for a frontier LLM.
Preserve the user's original intent and return only the improved prompt.
Do not invent, assume, or add any fact, name, number, date, or detail that is not explicitly stated in the original prompt or the clarifications below. If a detail is not covered by them, phrase the rewritten prompt so it explicitly asks for that detail or marks it as unspecified, rather than making one up.
Original prompt:
$INITIAL_PROMPT

Clarifications:
$conversation
EOF
)

log_entry "PROMPT" "ollama_enhancement" "$enhancement_prompt"
if ! enhanced_prompt=$(call_ollama "$enhancement_prompt"); then
  exit 1
fi
log_entry "OUTPUT" "ollama_enhancement" "$enhanced_prompt"

final_prompt=$(cat <<EOF
$enhanced_prompt

Accuracy constraints:
- Only use information explicitly given above; do not fabricate facts, sources, statistics, quotes, or other details.
- If something required to complete this task is missing or ambiguous, say so explicitly instead of guessing or filling it in.
- Clearly distinguish any assumption you must make from stated fact.
EOF
)

echo "Enhanced prompt:"
echo "$final_prompt"

if [[ -n "$OUTPUT_FILE" ]]; then
  printf '%s\n' "$final_prompt" > "$OUTPUT_FILE"
fi

if [[ -f "$FRONTIER_AGENT" ]]; then
  log_entry "PROMPT" "frontier" "$final_prompt"
  echo ""
  echo "Sending the optimized prompt to the configured frontier LLM agent..."
  frontier_response=$(python3 "$FRONTIER_AGENT" "$final_prompt" "$CONFIG_FILE")
  log_entry "OUTPUT" "frontier" "$frontier_response"
  echo "$frontier_response"
fi
