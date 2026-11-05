import json
from datetime import date, datetime, timedelta, timezone

import pytest

from ytdigest import cli, notify
from ytdigest.config import load_config, load_env
from ytdigest.digest import notification_title, render, split_message
from ytdigest.feeds import Video, parse_feed, parse_videos_page
from ytdigest.state import Seen
from ytdigest.summarize import build_prompt, parse_response

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">
 <title>Fireship</title>
 <entry>
  <yt:videoId>abcdefghijk</yt:videoId>
  <title>New JS framework</title>
  <published>2026-10-20T15:00:00+00:00</published>
  <media:group><media:description>It is fast.</media:description></media:group>
 </entry>
 <entry>
  <yt:videoId>zyxwvutsrqp</yt:videoId>
  <title>Old video</title>
  <published>2026-10-01T15:00:00+00:00</published>
 </entry>
</feed>"""


def test_parse_feed():
    videos = parse_feed(FEED, "Fireship")
    assert [v.id for v in videos] == ["abcdefghijk", "zyxwvutsrqp"]
    assert videos[0].title == "New JS framework"
    assert videos[0].description == "It is fast."
    assert videos[0].published == datetime(2026, 10, 20, 15, tzinfo=timezone.utc)
    assert videos[0].url == "https://www.youtube.com/watch?v=abcdefghijk"


def test_parse_videos_page_fallback():
    html = (
        '{"videoId":"AAAAAAAAAAA","thumbnail":{},"title":{"runs":[{"text":"First \\"quoted\\""}]}}'
        '{"videoId":"AAAAAAAAAAA","title":{"runs":[{"text":"dupe"}]}}'
        '{"videoId":"BBBBBBBBBBB","title":{"runs":[{"text":"Second"}]}}'
    )
    videos = parse_videos_page(html, "Theo")
    assert [(v.id, v.title) for v in videos] == [("AAAAAAAAAAA", 'First "quoted"'), ("BBBBBBBBBBB", "Second")]


def test_first_run_only_summarizes_recent(tmp_path):
    seen = Seen(tmp_path / "seen.json")
    videos = parse_feed(FEED, "Fireship")
    now = datetime(2026, 10, 21, 7, tzinfo=timezone.utc)
    new, backlog = cli.pick_new(videos, seen, 36, now)
    assert [v.id for v in new] == ["abcdefghijk"]
    assert [v.id for v in backlog] == ["zyxwvutsrqp"]


def test_later_runs_take_all_unseen(tmp_path):
    path = tmp_path / "seen.json"
    path.write_text(json.dumps(["abcdefghijk"]))
    seen = Seen(path)
    new, backlog = cli.pick_new(parse_feed(FEED, "Fireship"), seen, 36, datetime.now(timezone.utc))
    assert [v.id for v in new] == ["zyxwvutsrqp"] and backlog == []


def test_seen_roundtrip(tmp_path):
    seen = Seen(tmp_path / "s" / "seen.json")
    seen.add(["a", "b", "a"])
    seen.save()
    again = Seen(tmp_path / "s" / "seen.json")
    assert again.ids == ["a", "b"] and not again.first_run and "a" in again


def _videos():
    return [Video("v1", "Big launch", "Fireship"), Video("v2", "Drama", "Theo")]


def test_parse_response_keeps_missing_videos():
    raw = json.dumps({"headline": "H", "videos": [{"video_id": "v1", "verdict": "must_watch", "summary": "S", "why": "W"}, {"video_id": "bogus", "verdict": "skip", "summary": "", "why": ""}]})
    d = parse_response(raw, _videos())
    assert [(i.video.id, i.verdict) for i in d.items] == [("v1", "must_watch"), ("v2", "worth_skimming")]


def test_prompt_wraps_untrusted_content():
    p = build_prompt(_videos(), {"v1": "hello transcript", "v2": None})
    assert "<transcript>\nhello transcript\n</transcript>" in p
    assert "(none available)" in p


def test_render_and_title():
    raw = json.dumps({"headline": "AI news", "videos": [
        {"video_id": "v1", "verdict": "must_watch", "summary": "Launch.", "why": "Changes your stack."},
        {"video_id": "v2", "verdict": "skip", "summary": "Drama.", "why": "Noise."},
    ]})
    d = parse_response(raw, _videos())
    md = render(d, date(2026, 10, 21))
    assert md.index("Must watch") < md.index("Skip")
    assert "[Big launch](https://www.youtube.com/watch?v=v1)" in md
    assert "Worth skimming" not in md
    assert notification_title(d) == "🔥 Watch: Big launch"


def test_title_without_picks():
    d = parse_response(json.dumps({"headline": "", "videos": [{"video_id": "v2", "verdict": "skip", "summary": "", "why": ""}]}), _videos()[1:])
    assert notification_title(d) == "YouTube digest: 1 new video, nothing must-watch"


def test_split_message_respects_limit():
    md = "\n\n".join(f"Block {n} " + "x" * 300 for n in range(40))
    chunks = split_message(md, limit=1000)
    assert len(chunks) > 1
    assert all(len(c.encode()) <= 1000 for c in chunks)
    assert "".join(chunks).count("Block") == 40
    assert split_message("y" * 2500, limit=1000) == ["y" * 1000, "y" * 1000, "y" * 500]


def test_notify_posts_markdown(monkeypatch):
    sent = []

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return b""

    def fake_urlopen(req, timeout):
        sent.append(req)
        return Resp()

    monkeypatch.setenv("NTFY_TOPIC", "secret-topic")
    monkeypatch.setattr(notify.urllib.request, "urlopen", fake_urlopen)
    notify.send("🔥 Watch: thing", "**hi**", high_priority=True)
    req = sent[0]
    assert req.full_url == "https://ntfy.sh/secret-topic"
    assert req.get_header("Markdown") == "yes" and req.get_header("Priority") == "high"
    assert req.get_header("Title").startswith("=?UTF-8?B?")


def test_notify_requires_topic(monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    with pytest.raises(RuntimeError):
        notify.send("t", "m")


def test_repo_config_loads():
    from pathlib import Path
    cfg = load_config(Path(__file__).parents[1] / "config.toml")
    assert len(cfg.channels) == 5
    assert all(c.id.startswith("UC") for c in cfg.channels)


def test_load_env_does_not_override(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# c\nFOO_A=from_file\nFOO_B='quoted'\n")
    monkeypatch.setenv("FOO_A", "real")
    monkeypatch.delenv("FOO_B", raising=False)
    load_env(env)
    import os
    assert os.environ["FOO_A"] == "real" and os.environ["FOO_B"] == "quoted"
