
from __future__ import annotations

import subprocess
import os
import glob
from typing import TYPE_CHECKING, Optional
from pathlib import Path
from gi.repository import GLib

from .exceptions import DownloadError, ValidationError
from .logger import get_logger
from . import parsing

if TYPE_CHECKING:
    from .app_window import YouTubeAudioDownloader

logger = get_logger(__name__)


def build_ytdlp_command(
    url: str,
    download_path: str,
    audio_format: str = "mp3",
    use_auth: bool = False,
    auth_browser: str = "firefox",
    playlist_items: Optional[str] = None,
) -> list[str]:
    """Build the yt-dlp command for an audio download.

    For ``mp3`` the source audio is re-encoded to MP3 at 320k. For ``opus`` the
    native YouTube stream (already Opus) is copied into an .opus container with
    no re-encoding, so no bitrate post-processing is applied.
    """
    output_template = str(
        Path(download_path) / "%(playlist_index|)s%(playlist_index& - |)s%(title)s.%(ext)s"
    )

    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format", audio_format,
    ]

    # Only MP3 needs an explicit bitrate; Opus is copied, not re-encoded.
    if audio_format == "mp3":
        cmd.extend(["--postprocessor-args", "ffmpeg:-b:a 320k"])

    cmd.extend([
        "--embed-thumbnail",
        "--add-metadata",
        "--yes-playlist",
        "--ignore-errors",
        "--retries", "3",
        "--fragment-retries", "3",
        "--socket-timeout", "30",
        # Structured output we parse instead of guessing yt-dlp's free text.
        # --print forces quiet mode, so --no-quiet/--progress restore the info
        # and progress lines we still rely on; --newline keeps them line-delimited.
        "--no-quiet",
        "--newline",
        "--progress",
        "--progress-template", parsing.PROGRESS_TEMPLATE,
        "--progress-delta", "0.5",
        "--print", parsing.COMPLETED_TEMPLATE,
        "-o", output_template,
    ])

    if playlist_items:
        cmd.extend(["--playlist-items", playlist_items])

    if use_auth:
        cmd.extend(["--cookies-from-browser", auth_browser])

    cmd.append(url)
    return cmd


def download_thread(
    window: YouTubeAudioDownloader,
    url: str,
    url_type: str,
    download_path: str,
    use_auth: bool,
    auth_browser: str = "firefox",
    playlist_items: Optional[str] = None,
) -> None:
    """Run yt-dlp in a separate thread"""
    logger.info(f"Download thread started for {url_type}: {url}")

    # Every base path touched this run; swept for residual temp files in finally
    # (after the process exits), so even a "successful" download leaves nothing.
    all_download_bases: set[str] = set()

    try:
        # Validate download path
        if not download_path or not os.path.isdir(download_path):
            logger.error(f"Invalid download path: {download_path}")
            raise ValidationError(f"Download path is not a valid directory: {download_path}")

        if not os.access(download_path, os.W_OK):
            logger.error(f"Download path not writable: {download_path}")
            raise ValidationError(f"Download path is not writable: {download_path}")

        playlist_info = {}
        should_fetch_playlist_info = ((url_type == "Playlist") or use_auth) and not playlist_items
        if should_fetch_playlist_info:
            try:
                GLib.idle_add(window.log_message, "Getting playlist information...")
                logger.debug("Fetching playlist information...")
                info_cmd = [
                    "yt-dlp",
                    "--flat-playlist",
                    "--print",
                    "%(id)s:::%(playlist_index|)s%(playlist_index& - |)s%(title)s",
                ]
                if use_auth:
                    info_cmd.extend(["--cookies-from-browser", auth_browser])
                info_cmd.append(url)

                info_process = subprocess.run(
                    info_cmd,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if info_process.returncode == 0:
                    for line in info_process.stdout.strip().split('\n'):
                        if ':::' in line:
                            parts = line.split(':::', 1)
                            if len(parts) == 2:
                                video_id = parts[0].strip()
                                title = parts[1].strip()
                                playlist_info[video_id] = title
                    GLib.idle_add(
                        window.log_message,
                        "✓ Playlist information obtained: {} videos".format(len(playlist_info))
                    )
                    GLib.idle_add(window.log_message, "")
                    logger.info(f"Playlist info retrieved: {len(playlist_info)} videos")
                else:
                    logger.warning(f"Failed to get playlist info, return code: {info_process.returncode}")
            except subprocess.TimeoutExpired:
                logger.warning("Playlist info fetch timed out after 60 seconds")
                GLib.idle_add(window.log_message, "⚠ Playlist info fetch timed out, continuing anyway")
                GLib.idle_add(window.log_message, "")
            except subprocess.SubprocessError as e:
                logger.warning(f"Subprocess error getting playlist info: {e}")
                GLib.idle_add(window.log_message, "⚠ Could not get playlist info: {}".format(str(e)))
                GLib.idle_add(window.log_message, "")
            except Exception as e:
                logger.warning(f"Unexpected error getting playlist info: {e}")
                GLib.idle_add(window.log_message, "⚠ Could not get playlist info: {}".format(str(e)))
                GLib.idle_add(window.log_message, "")

        if window.download_cancel_requested.is_set():
            GLib.idle_add(window.log_message, "")
            GLib.idle_add(window.log_message, "✓ Download cancelled before starting")
            logger.info("Download cancelled by user before starting")
            return

        audio_format = getattr(window, "audio_format", "mp3")
        cmd = build_ytdlp_command(
            url,
            download_path,
            audio_format=audio_format,
            use_auth=use_auth,
            auth_browser=auth_browser,
            playlist_items=playlist_items,
        )

        format_label = "Opus (native, no conversion)" if audio_format == "opus" else "MP3 320k"
        GLib.idle_add(window.log_message, "🎵 Audio format: {}".format(format_label))
        GLib.idle_add(window.log_message, "")
        logger.info(f"Audio format: {audio_format}")

        if playlist_items:
            logger.info(f"Downloading selected playlist items: {playlist_items}")

        if use_auth:
            browser_name = auth_browser.capitalize()
            GLib.idle_add(window.log_message, "🔐 Authentication enabled: using {} cookies".format(browser_name))
            GLib.idle_add(window.log_message, "   (Make sure you are logged into YouTube in {})".format(browser_name))
            GLib.idle_add(window.log_message, "")
            logger.info("Using %s cookies for authentication", browser_name)

        GLib.idle_add(window.log_message, "Running: {}".format(' '.join(cmd)))
        GLib.idle_add(window.log_message, "")
        logger.debug(f"Executing command: {' '.join(cmd)}")

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
        except (OSError, subprocess.SubprocessError) as e:
            logger.error(f"Failed to start yt-dlp process: {e}")
            raise DownloadError(f"Could not start download process: {e}") from e

        with window.download_lock:
            window.current_process = process
        logger.debug(f"Download process started with PID: {process.pid}")

        current_video_title = ""
        successful_downloads = 0
        failed_downloads = 0
        skipped_downloads = 0
        skipped_videos = []
        failed_videos = []
        current_video_index = 0
        total_videos = 0
        # yt-dlp still runs postprocessors (and fires after_move -> [DONE]) on an
        # already-downloaded file, so a skipped item also emits a completion.
        # This flag lets the [DONE] handler avoid double-counting it as a success.
        current_item_skipped = False

        for line in process.stdout:
            line = line.strip()
            if not line:
                continue

            # --- Structured signals (parsed from templates we control) ---

            # Progress: update the bar, never echo the raw marker to the log
            progress = parsing.parse_progress(line)
            if progress is not None:
                GLib.idle_add(window.progress_bar.set_fraction, progress["percent"] / 100)
                if total_videos > 0:
                    progress_text = "Video {}/{} - {:.1f}%".format(
                        current_video_index, total_videos, progress["percent"]
                    )
                else:
                    progress_text = "{:.1f}%".format(progress["percent"])
                if progress["speed"]:
                    progress_text += " | {}".format(progress["speed"])
                if progress["eta"]:
                    progress_text += " | ETA {}".format(progress["eta"])
                GLib.idle_add(window.progress_bar.set_text, progress_text)
                continue

            # Completed: definitive success signal with the final filepath
            completed_path = parsing.parse_completed(line)
            if completed_path is not None:
                # A skipped file also reaches after_move; it was already counted
                if current_item_skipped:
                    current_item_skipped = False
                    continue
                successful_downloads += 1
                all_download_bases.add(os.path.splitext(completed_path)[0])
                window.queue_log_message("✓ Saved: {}".format(os.path.basename(completed_path)))
                logger.info(f"File completed: {completed_path}")
                if window.current_download_original:
                    with window.download_lock:
                        window.active_download_targets.discard(window.current_download_original)
                window.current_downloading_file = None
                window.current_download_original = None
                current_video_title = ""
                continue

            # --- Informational lines (logged verbatim) ---

            # Playlist position (computed before logging so we can label progress)
            item = parsing.parse_playlist_item(line)
            if item is not None:
                current_video_index, total_videos = item
                current_item_skipped = False
                if not current_video_title:
                    current_video_title = "Video #{}".format(current_video_index)

            window.queue_log_message(line)

            if "[download] Destination:" in line:
                try:
                    window.current_downloading_file = line.split("[download] Destination:")[1].strip()
                    window.current_download_original = window.current_downloading_file
                    with window.download_lock:
                        window.active_download_targets.add(window.current_download_original)

                    filename = os.path.basename(window.current_downloading_file)
                    current_video_title = os.path.splitext(filename)[0]

                    # Duplicate detection: check if the target audio file already exists
                    base, _ = os.path.splitext(window.current_downloading_file)
                    all_download_bases.add(base)
                    existing = base + "." + audio_format
                    if os.path.isfile(existing) and os.path.getsize(existing) > 1024:
                        existing_name = os.path.basename(existing)
                        msg = "⚠ Already exists: {} (skipped unless re-downloaded)".format(existing_name)
                        window.queue_log_message(msg)
                        logger.info(f"Duplicate detected: {existing_name}")
                except (IndexError, AttributeError) as e:
                    logger.debug(f"Could not parse destination from line: {e}")

            if parsing.is_skipped(line):
                skipped_downloads += 1
                current_item_skipped = True
                video_name = current_video_title or "Unknown"
                skipped_videos.append(video_name)
                window.queue_log_message("⏭ Skipped (already exists): {}".format(video_name))
                logger.info(f"Skipped duplicate: {video_name}")
                if window.current_download_original:
                    with window.download_lock:
                        window.active_download_targets.discard(window.current_download_original)
                window.current_downloading_file = None
                window.current_download_original = None
                current_video_title = ""

            # A video-level failure ('ERROR: [extractor] <id>: ...'); bare
            # postprocessor errors are logged above but not counted as failures.
            failed_video_id = parsing.parse_video_failure(line)
            if failed_video_id is not None:
                video_identifier = current_video_title
                if not video_identifier:
                    video_identifier = playlist_info.get(
                        failed_video_id, "ID: {}".format(failed_video_id)
                    )

                failed_downloads += 1
                failed_videos.append({"line": line, "video_context": video_identifier})
                if window.current_download_original:
                    with window.download_lock:
                        window.active_download_targets.discard(window.current_download_original)
                window.current_downloading_file = None
                window.current_download_original = None
                current_video_title = ""

            if item is not None:
                if total_videos > 0:
                    playlist_status = "Video {}/{}".format(current_video_index, total_videos)
                    GLib.idle_add(window.progress_bar.set_text, playlist_status)
                else:
                    GLib.idle_add(window.progress_bar.set_text, "Downloading playlist...")

        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            logger.warning("Process did not exit after stdout closed, killing")
            process.kill()
            process.wait(timeout=10)
        logger.info(f"Download process completed with return code: {process.returncode}")

        if window.download_stopped.is_set():
            GLib.idle_add(window.log_message, "")
            GLib.idle_add(window.log_message, "=" * 60)
            if successful_downloads > 0:
                msg = "ℹ Download stopped. Files completed before stopping: {}"
                GLib.idle_add(window.log_message, msg.format(successful_downloads))
                logger.info(f"Download stopped with {successful_downloads} files completed")
            else:
                GLib.idle_add(window.log_message, "ℹ Download stopped. No files were completed.")
                logger.info("Download stopped with no files completed")
            if skipped_downloads > 0:
                GLib.idle_add(window.log_message, "⏭ Skipped (already existed): {}".format(skipped_downloads))
            return

        if successful_downloads > 0:
            GLib.idle_add(window.progress_bar.set_fraction, 1.0)
            GLib.idle_add(window.log_message, "")
            GLib.idle_add(window.log_message, "=" * 60)

            if failed_downloads > 0:
                GLib.idle_add(window.progress_bar.set_text, "Completed with warnings")
                msg = "✓ Download completed: {} file(s) downloaded"
                GLib.idle_add(window.log_message, msg.format(successful_downloads))
                if skipped_downloads > 0:
                    msg = "⏭ Skipped (already existed): {}"
                    GLib.idle_add(window.log_message, msg.format(skipped_downloads))
                msg = "⚠ Warning: {} video(s) unavailable or failed"
                GLib.idle_add(window.log_message, msg.format(failed_downloads))
                logger.warning(
                    f"Download completed with {successful_downloads} successes, "
                    f"{skipped_downloads} skipped, {failed_downloads} failures"
                )

                if failed_videos:
                    GLib.idle_add(window.log_message, "")
                    GLib.idle_add(window.log_message, "Failed videos:")
                    GLib.idle_add(window.log_message, "-" * 60)
                    for i, failed in enumerate(failed_videos, 1):
                        GLib.idle_add(window.log_message, "{}. {}".format(i, failed['video_context']))
                        GLib.idle_add(window.log_message, "   Error: {}".format(failed['line']))
                    GLib.idle_add(window.log_message, "-" * 60)

                GLib.idle_add(
                    window.show_success_dialog,
                    "Download completed!\n\n✓ {} file(s) downloaded\n"
                    "⚠ {} video(s) unavailable".format(successful_downloads, failed_downloads)
                )
                GLib.idle_add(
                    window.send_notification,
                    "Download completed with warnings",
                    "{} file(s) downloaded, {} unavailable".format(
                        successful_downloads, failed_downloads
                    ),
                    "dialog-warning"
                )
            else:
                GLib.idle_add(window.progress_bar.set_text, "Completed!")
                msg = "✓ Download completed successfully: {} file(s)"
                GLib.idle_add(window.log_message, msg.format(successful_downloads))
                if skipped_downloads > 0:
                    msg = "⏭ Skipped (already existed): {}"
                    GLib.idle_add(window.log_message, msg.format(skipped_downloads))
                logger.info(
                    f"Download completed successfully: {successful_downloads} files, "
                    f"{skipped_downloads} skipped"
                )
                GLib.idle_add(
                    window.show_success_dialog,
                    "Download completed successfully!\n\n{} file(s) downloaded".format(
                        successful_downloads
                    )
                )
                GLib.idle_add(
                    window.send_notification,
                    "Download completed!",
                    "{} file(s) downloaded successfully".format(successful_downloads),
                    "emblem-default"
                )
        elif process.returncode == 0:
            GLib.idle_add(window.progress_bar.set_fraction, 1.0)
            GLib.idle_add(window.progress_bar.set_text, "Completed!")
            GLib.idle_add(window.log_message, "")
            GLib.idle_add(window.log_message, "=" * 60)
            GLib.idle_add(window.log_message, "✓ Process completed")
            logger.info("Process completed with return code 0 but no files downloaded")
            GLib.idle_add(window.show_success_dialog, "Process completed!")
            GLib.idle_add(
                window.send_notification,
                "Process completed",
                "The download process has finished",
                "dialog-information"
            )
        else:
            GLib.idle_add(window.progress_bar.set_text, "Error")
            GLib.idle_add(window.log_message, "")
            msg = "✗ Error: Could not download any files (code {})"
            GLib.idle_add(window.log_message, msg.format(process.returncode))
            logger.error(f"Download failed with return code {process.returncode}")
            GLib.idle_add(
                window.show_error_dialog,
                "Error: Could not download any files.\nCheck the log for more details."
            )

    except ValidationError as e:
        logger.error(f"Validation error in download: {e}")
        GLib.idle_add(window.log_message, "✗ Validation error: {}".format(str(e)))
        GLib.idle_add(window.show_error_dialog, "Validation error:\n{}".format(str(e)))
        GLib.idle_add(window.progress_bar.set_text, "Error")
    except DownloadError as e:
        logger.error(f"Download error: {e}")
        GLib.idle_add(window.log_message, "✗ Download error: {}".format(str(e)))
        GLib.idle_add(window.show_error_dialog, "Download error:\n{}".format(str(e)))
        GLib.idle_add(window.progress_bar.set_text, "Error")
    except Exception as e:
        logger.error(f"Unexpected error in download thread: {e}", exc_info=True)
        GLib.idle_add(window.log_message, "✗ Unexpected error: {}".format(str(e)))
        GLib.idle_add(window.show_error_dialog, "Unexpected error:\n{}".format(str(e)))
        GLib.idle_add(window.progress_bar.set_text, "Error")
    finally:
        with window.download_lock:
            window.current_process = None
            window.active_download_targets.clear()
        window.current_downloading_file = None
        window.current_download_original = None

        # The yt-dlp process has exited here, so no postprocessor still needs the
        # temp files. Sweep every base we touched — this catches residue from a
        # successful download too (e.g. an orphaned ".temp.opus"), not just stops.
        if all_download_bases:
            audio_format = getattr(window, "audio_format", "mp3")
            _remove_temp_artifacts(window, all_download_bases, audio_format)

        logger.debug("Download thread cleanup completed")

        def restore_download_button():
            window.download_button.set_sensitive(True)
            window.download_button.get_style_context().add_class("suggested-action")

        def restore_stop_button():
            window.stop_button.set_sensitive(False)
            window.stop_button.get_style_context().remove_class("destructive-action")

        GLib.idle_add(restore_download_button)
        GLib.idle_add(restore_stop_button)
        GLib.idle_add(window.copy_log_button.show)
        GLib.idle_add(window._set_ui_sensitive, True)


def temp_artifact_globs(base: str, audio_format: str) -> list[str]:
    """Glob patterns for yt-dlp temp/residual files sharing a base path.

    `base` is the path without extension (e.g. '/music/Song'). Covers the source
    container, fragments, every postprocessor working file ('<base>.temp.<ext>'
    from the metadata step, '<base>.meta'), and thumbnails. The completed output
    ('<base>.<audio_format>') is deliberately NOT included — finished files are
    never matched, so this is safe to run even after a successful download.
    """
    return [
        f"{base}.part",
        f"{base}.ytdl",
        f"{base}.temp",
        f"{base}.temp.*",
        f"{base}.meta",
        f"{base}.f*",
        f"{base}.fragment*",
        f"{base}.frag*",
        f"{base}.webm",
        f"{base}.webm.part",
        f"{base}.webm.ytdl",
        f"{base}.m4a",
        f"{base}.mp4",
        f"{base}.jpg",
        f"{base}.jpeg",
        f"{base}.png",
        f"{base}.webp",
    ]


def _remove_temp_artifacts(window: YouTubeAudioDownloader, bases, audio_format: str) -> int:
    """Remove temp/residual files for the given base paths. Returns count deleted.

    Only call this once the yt-dlp process has exited, so no postprocessor still
    needs the temp files. Completed output is preserved; a same-base final file
    is removed only when it is too small to be a real download (a partial).
    """
    files_deleted = 0
    for base in bases:
        try:
            for pattern in temp_artifact_globs(base, audio_format):
                for candidate in glob.glob(pattern):
                    try:
                        if os.path.isfile(candidate):
                            os.remove(candidate)
                            window.queue_log_message("🗑 Deleted: {}".format(os.path.basename(candidate)))
                            logger.debug(f"Deleted: {candidate}")
                            files_deleted += 1
                    except (OSError, PermissionError) as e:
                        logger.warning(f"Could not delete {candidate}: {e}")

            # Incomplete final audio (size guard so completed files survive)
            final = f"{base}.{audio_format}"
            try:
                if os.path.isfile(final) and os.path.getsize(final) < 1024:
                    os.remove(final)
                    window.queue_log_message("🗑 Deleted incomplete file: {}".format(os.path.basename(final)))
                    logger.debug(f"Deleted incomplete file: {final}")
                    files_deleted += 1
            except (OSError, PermissionError) as e:
                logger.warning(f"Could not process file {final}: {e}")
        except Exception as file_error:
            logger.error(f"Error cleaning base {base}: {file_error}")

    if files_deleted > 0:
        window.queue_log_message("✓ {} residual file(s) cleaned up".format(files_deleted))
        logger.info(f"Cleanup completed: {files_deleted} files deleted")
    return files_deleted


def cleanup_partial_files(window: YouTubeAudioDownloader) -> None:
    """Delete residual files for the currently tracked (in-progress) targets.

    Grabs and clears the target set under one lock so concurrent callers never
    double-process. Log output goes through the thread-safe queue.
    """
    logger.info("Starting cleanup of partial files")
    try:
        audio_format = getattr(window, "audio_format", "mp3")
        with window.download_lock:
            targets = list(window.active_download_targets)
            window.active_download_targets.clear()
        if not targets:
            return
        bases = {os.path.splitext(t)[0] for t in targets}
        _remove_temp_artifacts(window, bases, audio_format)
    except Exception as e:
        logger.error(f"Error in cleanup_partial_files: {e}", exc_info=True)
