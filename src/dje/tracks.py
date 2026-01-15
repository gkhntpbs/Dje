from dataclasses import dataclass
from typing import Optional

@dataclass
class Track:
    title: str
    webpage_url: str
    stream_url: str
    requested_by: str
    duration: Optional[int] = None
    source: str = "youtube"
    filepath: Optional[str] = None  # Local file path after download

