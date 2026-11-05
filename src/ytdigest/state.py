"""Remember which videos have already been covered so none repeat."""

import json
from pathlib import Path

KEEP = 2000  # plenty for 5 channels; keeps the file small


class Seen:
    def __init__(self, path: Path):
        self.path = path
        self.ids: list[str] = json.loads(path.read_text()) if path.exists() else []
        self.first_run = not path.exists()

    def __contains__(self, video_id: str) -> bool:
        return video_id in self.ids

    def add(self, video_ids) -> None:
        for vid in video_ids:
            if vid not in self.ids:
                self.ids.append(vid)
        self.ids = self.ids[-KEEP:]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.ids))
