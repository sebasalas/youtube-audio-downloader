"""Tests for youtubeaudiodownloader.download command building."""

import glob
import os
import threading

from youtubeaudiodownloader.download import (
    build_ytdlp_command,
    temp_artifact_globs,
    _remove_temp_artifacts,
)
from youtubeaudiodownloader import parsing


class _FakeWindow:
    """Minimal stand-in for the GTK window used by cleanup helpers."""

    def __init__(self, audio_format="opus"):
        self.download_lock = threading.Lock()
        self.active_download_targets = set()
        self.audio_format = audio_format
        self.logs = []

    def queue_log_message(self, message):
        self.logs.append(message)


def _pairs(cmd):
    """Helper: return set of (flag, value) for flags that take an argument."""
    return list(zip(cmd, cmd[1:]))


class TestBuildYtdlpCommand:
    """Tests for the pure yt-dlp command builder."""

    def test_starts_with_yt_dlp_and_extract_audio(self):
        cmd = build_ytdlp_command("https://youtu.be/abc", "/tmp")
        assert cmd[0] == "yt-dlp"
        assert "-x" in cmd

    def test_url_is_last_argument(self):
        url = "https://youtu.be/abc"
        cmd = build_ytdlp_command(url, "/tmp")
        assert cmd[-1] == url

    def test_mp3_uses_mp3_audio_format(self):
        cmd = build_ytdlp_command("u", "/tmp", audio_format="mp3")
        assert ("--audio-format", "mp3") in _pairs(cmd)

    def test_mp3_includes_320k_bitrate_postprocessor(self):
        cmd = build_ytdlp_command("u", "/tmp", audio_format="mp3")
        assert ("--postprocessor-args", "ffmpeg:-b:a 320k") in _pairs(cmd)

    def test_opus_uses_opus_audio_format(self):
        cmd = build_ytdlp_command("u", "/tmp", audio_format="opus")
        assert ("--audio-format", "opus") in _pairs(cmd)

    def test_opus_has_no_bitrate_postprocessor(self):
        """Opus is copied from the native source, never re-encoded to a bitrate."""
        cmd = build_ytdlp_command("u", "/tmp", audio_format="opus")
        assert "--postprocessor-args" not in cmd
        assert "320k" not in " ".join(cmd)

    def test_metadata_and_thumbnail_always_present(self):
        for fmt in ("mp3", "opus"):
            cmd = build_ytdlp_command("u", "/tmp", audio_format=fmt)
            assert "--add-metadata" in cmd
            assert "--embed-thumbnail" in cmd

    def test_auth_adds_cookies_from_browser(self):
        cmd = build_ytdlp_command("u", "/tmp", use_auth=True, auth_browser="brave")
        assert ("--cookies-from-browser", "brave") in _pairs(cmd)

    def test_no_auth_omits_cookies(self):
        cmd = build_ytdlp_command("u", "/tmp", use_auth=False)
        assert "--cookies-from-browser" not in cmd

    def test_playlist_items_included_when_given(self):
        cmd = build_ytdlp_command("u", "/tmp", playlist_items="1,3,5")
        assert ("--playlist-items", "1,3,5") in _pairs(cmd)

    def test_playlist_items_omitted_when_none(self):
        cmd = build_ytdlp_command("u", "/tmp", playlist_items=None)
        assert "--playlist-items" not in cmd

    def test_includes_structured_progress_template(self):
        cmd = build_ytdlp_command("u", "/tmp")
        assert ("--progress-template", parsing.PROGRESS_TEMPLATE) in _pairs(cmd)

    def test_includes_after_move_print_template(self):
        cmd = build_ytdlp_command("u", "/tmp")
        assert ("--print", parsing.COMPLETED_TEMPLATE) in _pairs(cmd)

    def test_includes_progress_delta_throttle(self):
        cmd = build_ytdlp_command("u", "/tmp")
        assert "--progress-delta" in cmd

    def test_restores_output_suppressed_by_print(self):
        # --print forces quiet; these must counteract it
        cmd = build_ytdlp_command("u", "/tmp")
        assert "--no-quiet" in cmd
        assert "--progress" in cmd
        assert "--newline" in cmd

    def test_output_template_targets_download_path(self):
        cmd = build_ytdlp_command("u", "/tmp/music")
        out_idx = cmd.index("-o")
        assert cmd[out_idx + 1].startswith("/tmp/music")
        assert cmd[out_idx + 1].endswith(".%(ext)s")


class TestTempArtifactGlobs:
    """Coverage for which yt-dlp temporary files get matched for cleanup."""

    def _matched(self, tmp_path, audio_format="opus"):
        base = str(tmp_path / "Song")
        matched = set()
        for pattern in temp_artifact_globs(base, audio_format):
            matched.update(glob.glob(pattern))
        return matched

    def test_cleans_metadata_temp_file(self, tmp_path):
        # The bug: "<base>.temp.opus" (metadata postprocessor) was left behind
        f = tmp_path / "Song.temp.opus"
        f.write_text("x")
        assert str(f) in self._matched(tmp_path)

    def test_cleans_meta_file(self, tmp_path):
        f = tmp_path / "Song.meta"
        f.write_text("x")
        assert str(f) in self._matched(tmp_path)

    def test_cleans_part_and_source_container(self, tmp_path):
        part = tmp_path / "Song.webm.part"
        webm = tmp_path / "Song.webm"
        part.write_text("x")
        webm.write_text("x")
        matched = self._matched(tmp_path)
        assert str(part) in matched
        assert str(webm) in matched

    def test_cleans_thumbnail_artifacts(self, tmp_path):
        webp = tmp_path / "Song.webp"
        png = tmp_path / "Song.png"
        webp.write_text("x")
        png.write_text("x")
        matched = self._matched(tmp_path)
        assert str(webp) in matched
        assert str(png) in matched

    def test_does_not_match_completed_final_audio(self, tmp_path):
        # The finished file must never be globbed for unconditional deletion
        final = tmp_path / "Song.opus"
        final.write_text("x" * 2000)
        assert str(final) not in self._matched(tmp_path)


class TestRemoveTempArtifacts:
    """End-to-end cleanup behavior against real files in a temp dir."""

    def test_removes_residue_keeps_completed_file(self, tmp_path):
        base = str(tmp_path / "Song")
        # The exact residue observed from a real opus download
        for suffix in (".webm", ".temp.opus", ".meta", ".webp", ".png"):
            (tmp_path / ("Song" + suffix)).write_text("x")
        (tmp_path / "Song.opus").write_text("x" * 5000)  # completed, must survive

        deleted = _remove_temp_artifacts(_FakeWindow(), {base}, "opus")

        assert deleted == 5
        assert os.path.exists(base + ".opus")
        for suffix in (".webm", ".temp.opus", ".meta", ".webp", ".png"):
            assert not os.path.exists(base + suffix)

    def test_removes_incomplete_final_audio(self, tmp_path):
        base = str(tmp_path / "Song")
        (tmp_path / "Song.opus").write_text("tiny")  # < 1024 bytes -> partial
        _remove_temp_artifacts(_FakeWindow(), {base}, "opus")
        assert not os.path.exists(base + ".opus")
