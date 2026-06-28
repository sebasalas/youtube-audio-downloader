"""Pure parsers for yt-dlp output.

These functions translate yt-dlp's textual output into structured data with no
side effects and no GTK dependency, so the parsing logic can be unit-tested in
isolation. ``download_thread`` consumes them to drive the UI.

The download command (see ``build_ytdlp_command``) is configured to emit two
controlled, prefixed lines via yt-dlp's own templating, so we parse values
computed by yt-dlp instead of guessing token positions:

- progress: ``--progress-template`` -> ``[PROG]<percent>|<speed>|<eta>``
- completed: ``--print after_move:`` -> ``[DONE]<final filepath>``
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

# Markers we control. yt-dlp fills the placeholders; we own the prefixes.
PROGRESS_TEMPLATE = (
    "download:[PROG]%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s"
)
COMPLETED_TEMPLATE = "after_move:[DONE]%(filepath)s"

_PROGRESS_PREFIX = "[PROG]"
_COMPLETED_PREFIX = "[DONE]"

_PLAYLIST_ITEM_RE = re.compile(r"Downloading (?:item|video) (\d+) of (\d+)")

# A video-level failure carries the extractor + id: "ERROR: [youtube] <id>: ...".
# Bare "ERROR: <message>" lines (e.g. postprocessor noise) are NOT video failures.
_VIDEO_FAILURE_RE = re.compile(r"^ERROR:\s*\[[^\]]+\]\s+([\w-]+):")


def _clean_value(value: str) -> Optional[str]:
    """Normalize a yt-dlp field; empty / NA / anything 'Unknown*' becomes None.

    yt-dlp emits placeholders like 'Unknown', 'Unknown B/s' or 'NA' when a value
    isn't available yet — none of those should reach the UI.
    """
    value = value.strip()
    low = value.lower()
    if not value or low in ("na", "n/a") or "unknown" in low:
        return None
    return value


def parse_progress(line: str) -> Optional[dict]:
    """Parse a ``[PROG]<percent>|<speed>|<eta>`` line.

    Returns a dict with ``percent`` (float), ``speed`` (str|None) and
    ``eta`` (str|None), or None if the line is not a well-formed progress line.
    """
    if not line.startswith(_PROGRESS_PREFIX):
        return None

    payload = line[len(_PROGRESS_PREFIX):]
    parts = payload.split("|")
    if len(parts) != 3:
        return None

    percent_raw = parts[0].strip().rstrip("%").strip()
    try:
        percent = float(percent_raw)
    except ValueError:
        return None

    return {
        "percent": percent,
        "speed": _clean_value(parts[1]),
        "eta": _clean_value(parts[2]),
    }


def parse_completed(line: str) -> Optional[str]:
    """Return the final filepath from a ``[DONE]<path>`` line, else None."""
    if not line.startswith(_COMPLETED_PREFIX):
        return None
    path = line[len(_COMPLETED_PREFIX):].strip()
    return path or None


def parse_playlist_item(line: str) -> Optional[Tuple[int, int]]:
    """Return (current, total) from a 'Downloading item N of M' line, else None."""
    match = _PLAYLIST_ITEM_RE.search(line)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def is_skipped(line: str) -> bool:
    """True if the line indicates yt-dlp skipped an already-downloaded file."""
    return "has already been downloaded" in line


def parse_error(line: str) -> Optional[str]:
    """Return the error line if it is any yt-dlp error, else None.

    Any line starting with 'ERROR:' counts — used for logging, not for counting
    failed videos (see parse_video_failure for that).
    """
    if line.strip().startswith("ERROR:"):
        return line.strip()
    return None


def parse_video_failure(line: str) -> Optional[str]:
    """Return the video id if the line is a video-level failure, else None.

    Matches yt-dlp's per-video error shape ('ERROR: [extractor] <id>: reason')
    regardless of the specific reason, so new failure modes are caught — while
    excluding bare postprocessor errors like 'ERROR: Conversion failed!' that do
    not mean a video failed.
    """
    match = _VIDEO_FAILURE_RE.match(line.strip())
    if not match:
        return None
    return match.group(1)
