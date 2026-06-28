"""Tests for youtubeaudiodownloader.utils module."""

import pytest

from youtubeaudiodownloader.utils import classify_youtube_url
from youtubeaudiodownloader.exceptions import ValidationError


class TestClassifyYoutubeUrl:
    """Tests for classify_youtube_url function."""

    # --- Valid URLs ---

    def test_standard_video_url(self):
        url_type, match = classify_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert url_type == "Video"
        assert match.group(1) == "dQw4w9WgXcQ"

    def test_video_url_without_www(self):
        url_type, _ = classify_youtube_url("https://youtube.com/watch?v=dQw4w9WgXcQ")
        assert url_type == "Video"

    def test_video_url_without_https(self):
        url_type, _ = classify_youtube_url("http://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert url_type == "Video"

    def test_short_url(self):
        url_type, match = classify_youtube_url("https://youtu.be/dQw4w9WgXcQ")
        assert url_type == "Video"
        assert match.group(1) == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        url_type, _ = classify_youtube_url("https://www.youtube.com/shorts/dQw4w9WgXcQ")
        assert url_type == "Short"

    def test_playlist_url(self):
        url_type, match = classify_youtube_url(
            "https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
        )
        assert url_type == "Playlist"

    def test_video_url_with_extra_params(self):
        url_type, match = classify_youtube_url(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLrAXtmErZgOe"
        )
        assert url_type == "Video"
        assert match.group(1) == "dQw4w9WgXcQ"

    def test_video_id_with_hyphens_and_underscores(self):
        url_type, match = classify_youtube_url("https://www.youtube.com/watch?v=abc-_DEF123")
        assert url_type == "Video"

    # --- Invalid URLs ---

    def test_empty_string(self):
        url_type, match = classify_youtube_url("")
        assert url_type is None
        assert match is None

    def test_whitespace_only(self):
        url_type, match = classify_youtube_url("   ")
        assert url_type is None
        assert match is None

    def test_random_string(self):
        url_type, _ = classify_youtube_url("not a url at all")
        assert url_type is None

    def test_non_youtube_url(self):
        url_type, _ = classify_youtube_url("https://www.google.com")
        assert url_type is None

    def test_invalid_video_id_too_short(self):
        url_type, _ = classify_youtube_url("https://www.youtube.com/watch?v=abc")
        assert url_type is None

    def test_long_video_id_matches_first_11(self):
        # Regex matches first 11 chars; extra chars become part of query string
        url_type, match = classify_youtube_url("https://www.youtube.com/watch?v=abcdefghijklm")
        assert url_type == "Video"
        assert len(match.group(1)) == 11

    # --- Error cases ---

    def test_none_raises_validation_error(self):
        with pytest.raises(ValidationError, match="URL cannot be None"):
            classify_youtube_url(None)

    def test_non_string_raises_validation_error(self):
        with pytest.raises(ValidationError, match="URL must be a string"):
            classify_youtube_url(123)

    # --- Whitespace handling ---

    def test_leading_trailing_whitespace(self):
        url_type, _ = classify_youtube_url("  https://www.youtube.com/watch?v=dQw4w9WgXcQ  ")
        assert url_type == "Video"
