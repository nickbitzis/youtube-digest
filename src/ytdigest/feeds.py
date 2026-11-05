"""Find each channel's latest videos.

Primary source is the channel's free RSS feed. YouTube's feeds intermittently
return 404/500, so we retry, then fall back to scraping the channel's Videos
page (no publish dates there; those videos are treated as new if unseen).
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime

from .config import Channel

FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"


@dataclass
class Video:
    id: str
    title: str
    channel: str
    published: datetime | None = None
    description: str = ""

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.id}"


def _get(url: str, timeout: float = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_feed(xml_text: str, channel_name: str) -> list[Video]:
    root = ET.fromstring(xml_text)
    videos = []
    for entry in root.findall("atom:entry", NS):
        vid = entry.findtext("yt:videoId", namespaces=NS)
        if not vid:
            continue
        published = entry.findtext("atom:published", namespaces=NS)
        videos.append(
            Video(
                id=vid,
                title=entry.findtext("atom:title", default="", namespaces=NS),
                channel=channel_name,
                published=datetime.fromisoformat(published) if published else None,
                description=entry.findtext("media:group/media:description", default="", namespaces=NS),
            )
        )
    return videos


def parse_videos_page(html: str, channel_name: str, limit: int = 15) -> list[Video]:
    """Pull video IDs and titles out of a channel's /videos page."""
    videos, seen = [], set()
    for m in re.finditer(r'"videoId":"([\w-]{11})".{0,400}?"title":\{"runs":\[\{"text":"((?:[^"\\]|\\.)*)"', html):
        vid, title = m.group(1), json.loads(f'"{m.group(2)}"')
        if vid not in seen:
            seen.add(vid)
            videos.append(Video(id=vid, title=title, channel=channel_name))
        if len(videos) >= limit:
            break
    return videos


def fetch_channel(channel: Channel, retries: int = 4, backoff: float = 2.0) -> list[Video]:
    last_error = None
    for attempt in range(retries):
        try:
            return parse_feed(_get(FEED_URL.format(channel.id)), channel.name)
        except (urllib.error.URLError, ET.ParseError, TimeoutError) as e:
            last_error = e
            time.sleep(backoff * (attempt + 1))
    try:
        page = _get(f"https://www.youtube.com/@{urllib.parse.quote(channel.handle)}/videos")
        videos = parse_videos_page(page, channel.name)
        if videos:
            return videos
    except urllib.error.URLError as e:
        last_error = e
    raise RuntimeError(f"Couldn't read {channel.name}: {last_error}")
