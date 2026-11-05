"""Turn a Digest into Markdown for the phone notification and the saved copy."""

from datetime import date

from .summarize import Digest

SECTIONS = [
    ("must_watch", "🔥 Must watch"),
    ("worth_skimming", "👀 Worth skimming"),
    ("skip", "⏭️ Skip (summary is enough)"),
]

# ntfy turns messages over 4096 bytes into file attachments; stay under it.
MAX_MESSAGE_BYTES = 3900


def render(digest: Digest, day: date) -> str:
    lines = [f"# YouTube digest — {day:%a %b %-d}", "", f"**{digest.headline}**", ""]
    for verdict, heading in SECTIONS:
        items = [i for i in digest.items if i.verdict == verdict]
        if not items:
            continue
        lines += [f"## {heading}", ""]
        for i in items:
            lines += [
                f"**[{i.video.title}]({i.video.url})** · {i.video.channel}",
                i.summary,
                f"_{i.why}_",
                "",
            ]
    return "\n".join(lines).strip() + "\n"


def notification_title(digest: Digest) -> str:
    picks = [i for i in digest.items if i.verdict == "must_watch"]
    n = len(digest.items)
    if picks:
        return f"🔥 Watch: {picks[0].video.title}" + (f" (+{len(picks) - 1} more)" if len(picks) > 1 else "")
    return f"YouTube digest: {n} new video{'s' if n != 1 else ''}, nothing must-watch"


def split_message(markdown: str, limit: int = MAX_MESSAGE_BYTES) -> list[str]:
    """Split on blank lines so each chunk fits in one notification."""
    chunks, current = [], ""
    for block in markdown.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate.encode()) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(block.encode()) > limit:  # a single giant block: hard-cut it
            cut = block.encode()[:limit].decode(errors="ignore")
            chunks.append(cut)
            block = block[len(cut):]
        current = block
    if current:
        chunks.append(current)
    return chunks
