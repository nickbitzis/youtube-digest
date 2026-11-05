"""Command line: `ytdigest run`, `ytdigest install`, `ytdigest test-notify`."""

import argparse
import os
import secrets
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import digest as digest_mod
from . import notify
from .config import load_config, load_env, runtime_home
from .feeds import Video, fetch_channel
from .state import Seen
from .summarize import summarize
from .transcripts import get_transcript

LABEL = "com.nickbitzis.youtube-digest"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def log(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def pick_new(videos: list[Video], seen: Seen, lookback_hours: int, now: datetime) -> tuple[list[Video], list[Video]]:
    """Split unseen videos into (to summarize, to just mark seen).

    On the first run, only recent videos count; the backlog is marked seen.
    """
    unseen = [v for v in videos if v.id not in seen]
    if not seen.first_run:
        return unseen, []
    cutoff = now - timedelta(hours=lookback_hours)
    recent = [v for v in unseen if v.published and v.published >= cutoff]
    return recent, [v for v in unseen if v not in recent]


def cmd_run(args) -> int:
    load_env()
    cfg = load_config()
    seen = Seen(cfg.home / "state" / "seen.json")
    now = datetime.now(timezone.utc)

    videos, errors = [], []
    for ch in cfg.channels:
        try:
            found = fetch_channel(ch)
            log(f"{ch.name}: {len(found)} in feed")
            videos += found
        except RuntimeError as e:
            log(f"ERROR {e}")
            errors.append(str(e))

    new, backlog = pick_new(videos, seen, cfg.first_run_lookback_hours, now)
    if args.limit:
        new = new[: args.limit]
    log(f"{len(new)} new video(s); {len(backlog)} older marked seen")

    if not new:
        seen.add(v.id for v in backlog)
        seen.save()
        if errors and not args.no_notify:
            notify.send("YouTube digest: couldn't check some channels", "\n\n".join(errors))
        return 0

    transcripts = {}
    for v in new:
        transcripts[v.id] = get_transcript(v.id)
        log(f"transcript {'ok' if transcripts[v.id] else 'MISSING'}: {v.title}")

    try:
        result = summarize(new, transcripts, cfg.model, cfg.effort, cfg.audience)
    except Exception as e:  # report the failure rather than fail silently
        log(f"ERROR summarizing: {e!r}")
        if not args.no_notify:
            titles = "\n".join(f"- [{v.title}]({v.url}) · {v.channel}" for v in new)
            notify.send("YouTube digest failed: here are today's titles", f"Summary step failed: {e}\n\n{titles}")
        return 1

    markdown = digest_mod.render(result, date.today())
    if errors:
        markdown += "\n_Couldn't check: " + "; ".join(errors) + "_\n"
    out = cfg.home / "digests" / f"{date.today():%Y-%m-%d}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown)
    log(f"saved {out}")
    print(markdown)

    if not args.no_notify:
        has_pick = any(i.verdict == "must_watch" for i in result.items)
        notify.send(digest_mod.notification_title(result), markdown, high_priority=has_pick)
        log("notification sent")
    else:
        return 0  # preview only: leave these videos for the real run

    seen.add([v.id for v in new] + [v.id for v in backlog])
    seen.save()
    return 0


def cmd_test_notify(args) -> int:
    load_env()
    notify.send("YouTube digest is connected ✅", "If you can read this, tomorrow's digest will reach you here.")
    log("test notification sent")
    return 0


def _plist(program: str, hour: int, minute: int, logs: Path) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key><array><string>{program}</string><string>run</string></array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>{hour}</integer><key>Minute</key><integer>{minute}</integer></dict>
  <key>StandardOutPath</key><string>{logs}/run.log</string>
  <key>StandardErrorPath</key><string>{logs}/run.log</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>{Path.home()}/.local/bin:/usr/bin:/bin</string></dict>
</dict>
</plist>
"""


def cmd_install(args) -> int:
    """Copy config + code out of ~/Documents and schedule the daily run."""
    root = Path(__file__).resolve().parents[2]
    if not (root / "config.toml").exists():
        sys.exit("Run install from the project folder: uv run ytdigest install")
    home = runtime_home()
    (home / "logs").mkdir(parents=True, exist_ok=True)
    shutil.copy(root / "config.toml", home / "config.toml")

    env = home / ".env"
    if not env.exists():
        env.write_text(
            "# Secrets for YouTube Digest. Not in git.\n"
            "ANTHROPIC_API_KEY=\n"
            f"NTFY_TOPIC=ytdigest-{secrets.token_urlsafe(18)}\n"
        )
        env.chmod(0o600)

    uv = shutil.which("uv") or str(Path.home() / ".local/bin/uv")
    subprocess.run([uv, "tool", "install", "--force", "--reinstall", "--python", "3.12", str(root)], check=True)
    program = str(Path.home() / ".local/bin/ytdigest")

    hour, minute = map(int, load_config(home / "config.toml").run_at.split(":"))
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_text(_plist(program, hour, minute, home / "logs"))
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", domain, str(PLIST)], capture_output=True)
    subprocess.run(["launchctl", "bootstrap", domain, str(PLIST)], check=True)
    log(f"installed; runs daily at {hour:02d}:{minute:02d}. Runtime folder: {home}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="ytdigest")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="check channels and send today's digest")
    run.add_argument("--no-notify", action="store_true", help="print the digest without sending it")
    run.add_argument("--limit", type=int, default=0, help="summarize at most N videos (testing)")
    sub.add_parser("install", help="install the scheduled daily job")
    sub.add_parser("test-notify", help="send a test notification")
    args = parser.parse_args()
    sys.exit({"run": cmd_run, "install": cmd_install, "test-notify": cmd_test_notify}[args.cmd](args))
