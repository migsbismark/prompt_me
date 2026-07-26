#!/usr/bin/env bash
set -euo pipefail

if command -v ollama >/dev/null 2>&1; then
  echo "Starting Ollama in the background..."
  ollama serve > /tmp/ollama.log 2>&1 &
  for _ in $(seq 1 30); do
    if curl -sSf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

exec "$@"
