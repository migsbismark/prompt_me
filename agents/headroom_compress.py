#!/usr/bin/env python3
"""CLI bridge so ollama_agent.sh (bash) can compress a message history with
Headroom without reimplementing the Python call. Reads a JSON messages array
on stdin, writes the compressed JSON messages array to stdout.

Usage: ./headroom_compress.py [model]
"""
import json
import sys

from headroom_util import compress_messages


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else None
    messages = json.load(sys.stdin)
    print(json.dumps(compress_messages(messages, model)))


if __name__ == "__main__":
    main()
