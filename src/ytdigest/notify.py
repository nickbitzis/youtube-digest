"""Push the digest to your phone through ntfy (https://ntfy.sh).

The topic name acts as the password: anyone who knows it can read the
channel, so it's a long random string kept in .env, never in the repo.
"""

import os
import urllib.request

from .digest import split_message


def send(title: str, markdown: str, high_priority: bool = False) -> None:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        raise RuntimeError("NTFY_TOPIC is not set in .env")
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    chunks = split_message(markdown)
    for n, chunk in enumerate(chunks, 1):
        chunk_title = title if len(chunks) == 1 else f"{title} ({n}/{len(chunks)})"
        req = urllib.request.Request(
            f"{server}/{topic}",
            data=chunk.encode(),
            method="POST",
            headers={
                # HTTP headers must be latin-1; ntfy accepts RFC 2047 for emoji/unicode.
                "Title": _encode_header(chunk_title),
                "Markdown": "yes",
                "Priority": "high" if high_priority and n == 1 else "default",
                "Tags": "tv",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()


def _encode_header(value: str) -> str:
    try:
        value.encode("latin-1")
        return value
    except UnicodeEncodeError:
        import base64

        return "=?UTF-8?B?" + base64.b64encode(value.encode()).decode() + "?="
