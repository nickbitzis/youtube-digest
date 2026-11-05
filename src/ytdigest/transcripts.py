"""Fetch a video's captions as plain text (YouTube's auto-captions are fine)."""

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import CouldNotRetrieveTranscript


def get_transcript(video_id: str) -> str | None:
    try:
        fetched = YouTubeTranscriptApi().fetch(video_id, languages=["en", "en-US", "en-GB"])
    except CouldNotRetrieveTranscript:
        return None
    return " ".join(s.text.replace("\n", " ") for s in fetched).strip() or None
