"""Tests for youtubeaudiodownloader.parsing — pure yt-dlp output parsers."""

from youtubeaudiodownloader.parsing import (
    parse_progress,
    parse_completed,
    parse_playlist_item,
    is_skipped,
    parse_error,
    parse_video_failure,
    PROGRESS_TEMPLATE,
    COMPLETED_TEMPLATE,
)


class TestParseProgress:
    def test_full_progress_line(self):
        result = parse_progress("[PROG] 42.3%|1.23MiB/s|00:42")
        assert result == {"percent": 42.3, "speed": "1.23MiB/s", "eta": "00:42"}

    def test_percent_with_leading_spaces(self):
        result = parse_progress("[PROG]100.0%|5.00MiB/s|00:00")
        assert result["percent"] == 100.0

    def test_unknown_speed_and_eta_become_none(self):
        result = parse_progress("[PROG] 10.0%|Unknown|Unknown")
        assert result["percent"] == 10.0
        assert result["speed"] is None
        assert result["eta"] is None

    def test_unknown_bytes_per_sec_speed_becomes_none(self):
        # yt-dlp emits "Unknown B/s" early in a download
        result = parse_progress("[PROG]  0.4%| Unknown B/s|Unknown")
        assert result["speed"] is None

    def test_na_eta_becomes_none(self):
        result = parse_progress("[PROG]100.0%|6.01MiB/s|NA")
        assert result["eta"] is None
        assert result["speed"] == "6.01MiB/s"

    def test_non_progress_line_returns_none(self):
        assert parse_progress("[download] Destination: foo.webm") is None

    def test_malformed_progress_returns_none(self):
        assert parse_progress("[PROG]garbage") is None


class TestParseCompleted:
    def test_extracts_filepath(self):
        assert parse_completed("[DONE]/home/u/Music/song.opus") == "/home/u/Music/song.opus"

    def test_path_with_spaces(self):
        assert parse_completed("[DONE]/home/u/My Song - Live.mp3") == "/home/u/My Song - Live.mp3"

    def test_non_done_line_returns_none(self):
        assert parse_completed("[download] 100%") is None


class TestParsePlaylistItem:
    def test_downloading_item(self):
        assert parse_playlist_item("[download] Downloading item 3 of 10") == (3, 10)

    def test_downloading_video(self):
        assert parse_playlist_item("[download] Downloading video 1 of 5") == (1, 5)

    def test_non_item_line_returns_none(self):
        assert parse_playlist_item("[download] 50%") is None


class TestIsSkipped:
    def test_already_downloaded(self):
        assert is_skipped("[download] song.opus has already been downloaded") is True

    def test_regular_line(self):
        assert is_skipped("[download] Destination: song.opus") is False


class TestParseError:
    def test_error_line_returns_message(self):
        line = "ERROR: [youtube] abc123: Video unavailable"
        assert parse_error(line) == line

    def test_error_with_leading_whitespace(self):
        assert parse_error("  ERROR: something failed") == "ERROR: something failed"

    def test_non_error_returns_none(self):
        assert parse_error("[download] 100%") is None

    def test_arbitrary_error_is_caught(self):
        """Any ERROR: counts, not just a hardcoded whitelist."""
        line = "ERROR: some brand new failure mode yt-dlp invented"
        assert parse_error(line) == line


class TestParseVideoFailure:
    def test_youtube_video_failure_returns_id(self):
        line = "ERROR: [youtube] jNQXAC9IVRw: Video unavailable"
        assert parse_video_failure(line) == "jNQXAC9IVRw"

    def test_extractor_with_colon_returns_id(self):
        line = "ERROR: [youtube:tab] PLabc123: This playlist is private"
        assert parse_video_failure(line) == "PLabc123"

    def test_postprocessor_error_is_not_a_video_failure(self):
        # Non-fatal postprocessor noise must NOT be counted as a failed video
        assert parse_video_failure("ERROR: Conversion failed!") is None

    def test_non_error_line_returns_none(self):
        assert parse_video_failure("[download] 100%") is None


class TestTemplates:
    def test_progress_template_is_download_scoped(self):
        assert PROGRESS_TEMPLATE.startswith("download:")
        assert "[PROG]" in PROGRESS_TEMPLATE

    def test_completed_template_is_after_move(self):
        assert COMPLETED_TEMPLATE.startswith("after_move:")
        assert "[DONE]" in COMPLETED_TEMPLATE
