"""Settings and runtime paths.

The scheduled job can't read ~/Documents (macOS privacy rules block background
jobs there), so everything it needs at run time lives in the runtime home:
config copy, .env, seen-video state, saved digests, and logs.
"""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_HOME = Path.home() / "Library" / "Application Support" / "youtube-digest"


def runtime_home() -> Path:
    return Path(os.environ.get("YTDIGEST_HOME", DEFAULT_HOME))


@dataclass
class Channel:
    name: str
    handle: str
    id: str


@dataclass
class Config:
    channels: list[Channel]
    run_at: str = "07:00"
    first_run_lookback_hours: int = 36
    model: str = "claude-opus-5-5"
    effort: str = "medium"
    audience: str = ""
    home: Path = field(default_factory=runtime_home)


def load_config(path: Path | None = None) -> Config:
    path = path or runtime_home() / "config.toml"
    data = tomllib.loads(path.read_text())
    channels = [Channel(**c) for c in data.pop("channels")]
    return Config(channels=channels, **data)


def load_env(path: Path | None = None) -> None:
    """Load KEY=VALUE lines from the runtime .env without overriding real env vars."""
    path = path or runtime_home() / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
