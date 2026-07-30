#!/usr/bin/env python3
from headroom import compress


def compress_messages(messages: list, model: str = None) -> list:
    """Compress a list of {role, content} messages with Headroom, returning
    the compressed messages. Used right before messages go out over the
    network -- never mutates whatever history is stored on disk."""
    kwargs = {"model": model} if model else {}
    return compress(messages, **kwargs).messages
