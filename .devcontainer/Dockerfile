FROM ghcr.io/anthropics/claude-code:latest

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    jq \
    python3 \
    && rm -rf /var/lib/apt/lists/*
