import re
from typing import Optional, Tuple

from .exceptions import ValidationError
from .logger import get_logger

logger = get_logger(__name__)

# Precompiled patterns to validate and classify YouTube URLs
YOUTUBE_PATTERNS = [
    (re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([\w-]{11})'), "Video"),
    (re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/playlist\?list=([\w-]{13,})'), "Playlist"),
    (re.compile(r'(?:https?://)?youtu\.be/([\w-]{11})'), "Video"),
    (re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/shorts/([\w-]{11})'), "Short"),
]


def classify_youtube_url(url: str) -> Tuple[Optional[str], Optional[re.Match]]:
    """
    Classify and validate a YouTube URL.

    Args:
        url: The URL string to classify

    Returns:
        A tuple of (url_type, match_object) where:
        - url_type is one of "Video", "Playlist", "Short", or None if invalid
        - match_object is the regex match object, or None if invalid

    Raises:
        ValidationError: If the input is None or empty
    """
    if url is None:
        logger.warning("classify_youtube_url received None as input")
        raise ValidationError("URL cannot be None")

    if not isinstance(url, str):
        logger.warning(f"classify_youtube_url received non-string input: {type(url)}")
        raise ValidationError(f"URL must be a string, not {type(url).__name__}")

    cleaned_url = url.strip()

    if not cleaned_url:
        logger.debug("Empty URL provided")
        return None, None

    for pattern, url_type in YOUTUBE_PATTERNS:
        match = pattern.match(cleaned_url)
        if match:
            logger.debug(f"URL classified as {url_type}: {cleaned_url}")
            return url_type, match

    logger.debug(f"URL not recognized as valid YouTube URL: {cleaned_url}")
    return None, None
