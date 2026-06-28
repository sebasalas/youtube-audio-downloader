import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Gio  # noqa: E402
import subprocess  # noqa: E402
import threading  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
from pathlib import Path  # noqa: E402

from . import config  # noqa: E402
from . import utils  # noqa: E402
from . import download  # noqa: E402
from .dialogs import PlaylistPreviewDialog  # noqa: E402
from .exceptions import ValidationError  # noqa: E402
from .logger import get_logger  # noqa: E402

logger = get_logger(__name__)


class YouTubeAudioDownloader(Gtk.Window):
    def __init__(self):
        super().__init__(title="YouTube Audio Downloader")
        self.set_border_width(10)

        # Load persistent configuration
        self.config = config.load_config()

        # Default download directory (or loaded from config)
        self.download_path = self.config.get('download_path', str(Path.home() / "Downloads"))

        # YouTube authentication status (loaded from config)
        self.use_youtube_auth = self.config.get('use_youtube_auth', False)

        # Notification status (loaded from config)
        self.notifications_enabled = self.config.get('notifications_enabled', True)

        # Audio output format: "mp3" (re-encoded 320k) or "opus" (native, no conversion)
        self.audio_format = self.config.get('audio_format', config.DEFAULT_AUDIO_FORMAT)

        # Current download process
        self.current_process = None
        self.download_stopped = threading.Event()
        self.download_cancel_requested = threading.Event()
        self.current_downloading_file = None
        self.current_download_original = None
        self.download_lock = threading.Lock()
        self.active_download_targets = set()
        self._download_thread = None

        # Batched log output: the worker thread enqueues lines and the main loop
        # flushes them together, avoiding one GLib.idle_add per stdout line on
        # large playlists.
        self._log_pending = []
        self._log_flush_scheduled = False
        self._log_lock = threading.Lock()

        # Apply saved window size
        window_width = self.config.get('window_width', 600)
        window_height = self.config.get('window_height', 400)
        self.set_default_size(window_width, window_height)

        # Apply saved window position (if it exists)
        if 'window_x' in self.config and 'window_y' in self.config:
            self.move(self.config['window_x'], self.config['window_y'])
            # Do not center if we already have a saved position
        else:
            self.set_position(Gtk.WindowPosition.CENTER)

        # Connect close event to save configuration
        self.connect("delete-event", self.on_delete_event)

        # Create HeaderBar
        self.setup_headerbar()

        # Create interface
        self.setup_ui()

    def setup_headerbar(self):
        """Set up the top bar with a menu"""
        headerbar = Gtk.HeaderBar()
        headerbar.set_show_close_button(True)
        headerbar.props.title = "YouTube Audio Downloader"
        self.set_titlebar(headerbar)

        # Hamburger menu button
        menu_button = Gtk.MenuButton()
        menu_icon = Gio.ThemedIcon(name="open-menu-symbolic")
        menu_image = Gtk.Image.new_from_gicon(menu_icon, Gtk.IconSize.BUTTON)
        menu_button.add(menu_image)
        menu_button.set_tooltip_text("Menu")

        # Create the menu
        menu = Gio.Menu()
        menu.append("Preferences", "app.show-preferences")

        # Set up the menu popover
        popover = Gtk.Popover.new_from_model(menu_button, menu)
        menu_button.set_popover(popover)

        # Add the menu button to the right side of the headerbar
        headerbar.pack_end(menu_button)

    def setup_ui(self):
        # Main vertical box
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(vbox)

        # URL Input
        url_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        url_label = Gtk.Label(label="YouTube URL:")
        url_label.set_size_request(120, -1)
        url_label.set_xalign(0)
        self.url_entry = Gtk.Entry()
        self.url_entry.set_placeholder_text("YouTube video or playlist URL...")
        self.url_entry.connect("changed", self.on_url_changed)

        # Button to clear URL
        self.clear_url_button = Gtk.Button()
        clear_url_icon = Gio.ThemedIcon(name="edit-clear-symbolic")
        clear_url_image = Gtk.Image.new_from_gicon(clear_url_icon, Gtk.IconSize.BUTTON)
        self.clear_url_button.add(clear_url_image)
        self.clear_url_button.set_tooltip_text("Clear URL")
        self.clear_url_button.connect("clicked", self.on_clear_url_clicked)

        # Button to paste URL
        self.paste_url_button = Gtk.Button()
        paste_url_icon = Gio.ThemedIcon(name="edit-paste-symbolic")
        paste_url_image = Gtk.Image.new_from_gicon(paste_url_icon, Gtk.IconSize.BUTTON)
        self.paste_url_button.add(paste_url_image)
        self.paste_url_button.set_tooltip_text("Paste URL from clipboard")
        self.paste_url_button.connect("clicked", self.on_paste_url_clicked)

        # URL validation indicator
        self.url_status_label = Gtk.Label()
        self.url_status_label.set_text("")
        self.url_status_label.set_size_request(20, -1)

        url_box.pack_start(url_label, False, False, 0)
        url_box.pack_start(self.url_entry, True, True, 0)
        url_box.pack_start(self.paste_url_button, False, False, 0)  # Add paste button
        url_box.pack_start(self.clear_url_button, False, False, 0)
        url_box.pack_start(self.url_status_label, False, False, 0)
        vbox.pack_start(url_box, False, False, 0)

        # Destination folder
        folder_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        folder_label = Gtk.Label(label="Destination folder:")
        folder_label.set_size_request(120, -1)
        folder_label.set_xalign(0)
        self.folder_entry = Gtk.Entry()
        self.folder_entry.set_text(self.download_path)
        self.folder_entry.set_editable(False)
        self.folder_button = Gtk.Button(label="Select...")
        self.folder_button.connect("clicked", self.on_select_folder)

        # Button to open folder
        self.open_folder_button = Gtk.Button()
        open_folder_icon = Gio.ThemedIcon(name="folder-open-symbolic")
        open_folder_image = Gtk.Image.new_from_gicon(open_folder_icon, Gtk.IconSize.BUTTON)
        self.open_folder_button.add(open_folder_image)
        self.open_folder_button.set_tooltip_text("Open destination folder")
        self.open_folder_button.connect("clicked", self.on_open_folder)

        folder_box.pack_start(folder_label, False, False, 0)
        folder_box.pack_start(self.folder_entry, True, True, 0)
        folder_box.pack_start(self.folder_button, False, False, 0)
        folder_box.pack_start(self.open_folder_button, False, False, 0)
        vbox.pack_start(folder_box, False, False, 0)

        # Download and stop buttons
        buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.download_button = Gtk.Button(label=self._download_button_label())
        self.download_button.connect("clicked", self.on_download_clicked)
        self.download_button.get_style_context().add_class("suggested-action")  # Always visible

        self.stop_button = Gtk.Button(label="⏹ Stop")
        self.stop_button.connect("clicked", self.on_stop_clicked)
        # Do not add "destructive-action" at the beginning because it is disabled
        self.stop_button.set_sensitive(False)  # Initially disabled

        buttons_box.pack_start(self.download_button, True, True, 0)
        buttons_box.pack_start(self.stop_button, True, True, 0)
        vbox.pack_start(buttons_box, False, False, 5)

        # Progress bar
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        self.progress_bar.set_text("Waiting...")
        vbox.pack_start(self.progress_bar, False, False, 0)

        # Log/status area
        log_label = Gtk.Label(label="Log:")
        log_label.set_xalign(0)
        vbox.pack_start(log_label, False, False, 0)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_vexpand(True)
        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        self.log_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.log_buffer = self.log_view.get_buffer()
        scrolled_window.add(self.log_view)
        vbox.pack_start(scrolled_window, True, True, 0)

        # Button to copy log (only visible when finished)
        self.copy_log_button = Gtk.Button(label="📋 Copy full log")
        self.copy_log_button.connect("clicked", self.on_copy_log_clicked)
        self.copy_log_button.set_no_show_all(True)  # Do not show by default
        self.copy_log_button.hide()  # Initially hidden
        vbox.pack_start(self.copy_log_button, False, False, 5)

    def _download_button_label(self):
        """Label reflecting the active audio format, so the button never lies."""
        if self.audio_format == "opus":
            return "⬇ Download Opus"
        return "⬇ Download MP3 320"

    def update_download_button_label(self):
        """Refresh the download button label after the audio format changes."""
        self.download_button.set_label(self._download_button_label())

    def _set_ui_sensitive(self, sensitive):
        """Sets the sensitivity of UI elements that should be disabled during download."""
        self.url_entry.set_sensitive(sensitive)
        self.folder_button.set_sensitive(sensitive)
        self.open_folder_button.set_sensitive(sensitive)
        self.clear_url_button.set_sensitive(sensitive)
        self.paste_url_button.set_sensitive(sensitive)

    def on_paste_url_clicked(self, button):
        """Paste URL from clipboard"""
        try:
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            text = clipboard.wait_for_text()
            if text:
                self.url_entry.set_text(text)
                self.url_entry.grab_focus()
                logger.debug("URL pasted from clipboard")
            else:
                logger.debug("Clipboard is empty")
        except Exception as e:
            logger.error(f"Failed to paste from clipboard: {e}")
            self.show_error_dialog(f"Could not paste from clipboard:\n{str(e)}")

    def on_select_folder(self, button):
        """Open dialog to select folder"""
        try:
            dialog = Gtk.FileChooserDialog(
                title="Select destination folder",
                parent=self,
                action=Gtk.FileChooserAction.SELECT_FOLDER
            )
            dialog.add_buttons(
                Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                Gtk.STOCK_OPEN, Gtk.ResponseType.OK
            )

            # Try to set current folder, but don't fail if it doesn't exist
            try:
                if os.path.isdir(self.download_path):
                    dialog.set_current_folder(self.download_path)
            except (OSError, TypeError) as e:
                logger.warning(f"Could not set current folder in dialog: {e}")

            response = dialog.run()
            if response == Gtk.ResponseType.OK:
                self.download_path = dialog.get_filename()
                self.folder_entry.set_text(self.download_path)
                # Save download path in configuration
                self.config['download_path'] = self.download_path
                try:
                    config.save_config(self.config)
                    logger.info(f"Download path updated: {self.download_path}")
                except Exception as e:
                    logger.error(f"Failed to save download path: {e}")

            dialog.destroy()
        except Exception as e:
            logger.error(f"Error in folder selection dialog: {e}")
            self.show_error_dialog(f"Could not open folder selection dialog:\n{str(e)}")

    def on_open_folder(self, button):
        """Open destination folder in the file explorer"""
        try:
            # Validate that the folder exists
            if not os.path.isdir(self.download_path):
                logger.warning(f"Download folder does not exist: {self.download_path}")
                self.show_error_dialog(f"Folder does not exist:\n{self.download_path}")
                return

            # Check if xdg-open is available
            if shutil.which("xdg-open"):
                subprocess.Popen(
                    ["xdg-open", self.download_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                logger.debug(f"Opened folder: {self.download_path}")
            else:
                logger.error("xdg-open not found")
                self.show_error_dialog(
                    "Cannot open folder: xdg-open is not installed.\n"
                    f"Folder path: {self.download_path}"
                )
        except subprocess.SubprocessError as e:
            logger.error(f"Failed to open folder with xdg-open: {e}")
            self.show_error_dialog(f"Could not open folder:\n{str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error opening folder: {e}")
            self.show_error_dialog(f"Could not open folder:\n{str(e)}")

    def on_url_changed(self, entry):
        """Validate URL in real time and update visual indicator"""
        url = entry.get_text().strip()

        if not url:
            # Empty field
            self.url_status_label.set_text("")
            self.url_status_label.set_tooltip_text("")
            return

        try:
            url_type, _ = utils.classify_youtube_url(url)

            if url_type:
                self.url_status_label.set_markup("<span foreground='green' size='large'>✓</span>")
                self.url_status_label.set_tooltip_text("Valid YouTube URL ({})".format(url_type))
            else:
                self.url_status_label.set_markup("<span foreground='red' size='large'>✗</span>")
                self.url_status_label.set_tooltip_text("Invalid YouTube URL")
        except ValidationError as e:
            logger.error(f"Validation error in URL check: {e}")
            self.url_status_label.set_markup("<span foreground='red' size='large'>✗</span>")
            self.url_status_label.set_tooltip_text("Invalid input")
        except Exception as e:
            logger.error(f"Unexpected error validating URL: {e}")

    def on_clear_url_clicked(self, button):
        """Clear the URL field"""
        self.url_entry.set_text("")
        self.url_entry.grab_focus()

    def on_delete_event(self, widget, event):
        """Save window configuration and gracefully stop downloads before closing"""
        # Signal any running download to stop
        self.download_stopped.set()
        self.download_cancel_requested.set()

        with self.download_lock:
            process = self.current_process
        if process:
            try:
                process.terminate()
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            except Exception as e:
                logger.warning(f"Error terminating process on close: {e}")

        # Wait for download thread to finish
        if self._download_thread and self._download_thread.is_alive():
            self._download_thread.join(timeout=3)

        try:
            # Get current window size
            width, height = self.get_size()
            self.config['window_width'] = width
            self.config['window_height'] = height

            # Get current window position
            x, y = self.get_position()
            self.config['window_x'] = x
            self.config['window_y'] = y

            # Save configuration
            config.save_config(self.config)
            logger.info("Window configuration saved")
        except Exception as e:
            logger.error(f"Failed to save window configuration: {e}")

        # Return False to allow the window to close normally
        return False

    def send_notification(self, title, message, icon="dialog-information"):
        """Send system notification if enabled"""
        if not self.notifications_enabled:
            logger.debug("Notifications disabled, skipping")
            return

        # Try Gio.Notification first (native GTK)
        try:
            notification = Gio.Notification.new(title)
            notification.set_body(message)

            # Set icon
            if icon == "dialog-information":
                notification.set_icon(Gio.ThemedIcon.new("dialog-information"))
            elif icon == "dialog-warning":
                notification.set_icon(Gio.ThemedIcon.new("dialog-warning"))
            elif icon == "emblem-default":
                notification.set_icon(Gio.ThemedIcon.new("emblem-default"))

            # Send notification through the application
            app = self.get_application()
            if app:
                app.send_notification(None, notification)
                logger.debug(f"Notification sent via Gio: {title}")
                return
        except Exception as e:
            logger.debug(f"Gio notification failed: {e}")

        # Fallback: use notify-send if available
        if shutil.which("notify-send"):
            try:
                subprocess.run([
                    "notify-send",
                    "-a", "YouTube Audio Downloader",
                    "-i", icon,
                    title,
                    message
                ], check=False, timeout=5,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
                logger.debug(f"Notification sent via notify-send: {title}")
                return
            except subprocess.TimeoutExpired:
                logger.warning("notify-send timed out")
            except subprocess.SubprocessError as e:
                logger.warning(f"notify-send failed: {e}")
            except Exception as e:
                logger.warning(f"Unexpected error with notify-send: {e}")
        else:
            logger.debug("notify-send not available")

        # Silent fail - notifications are optional
        logger.debug("All notification methods failed, continuing without notification")

    def on_copy_log_clicked(self, button):
        """Copy all log content to the clipboard"""
        try:
            # Get all text from the buffer
            start_iter = self.log_buffer.get_start_iter()
            end_iter = self.log_buffer.get_end_iter()
            log_text = self.log_buffer.get_text(start_iter, end_iter, True)

            # Copy to clipboard
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(log_text, -1)
            clipboard.store()

            # Show confirmation in the log
            self.log_message("")
            self.log_message("✓ Log copied to clipboard")
            logger.debug("Log copied to clipboard")
        except Exception as e:
            logger.error(f"Failed to copy log to clipboard: {e}")
            self.show_error_dialog(f"Could not copy log:\n{str(e)}")

    def on_stop_clicked(self, button):
        """Stop the current download process"""
        self.log_message("")
        self.log_message("⏹ Stopping download...")
        logger.info("User requested download stop")

        # Mark as stopped and request cancellation
        self.download_stopped.set()
        self.download_cancel_requested.set()

        # If there is a running process, terminate it
        with self.download_lock:
            process = self.current_process
        if process:
            try:
                process.terminate()  # Try to terminate gracefully
                logger.debug("Sent terminate signal to download process")
                # Give time to terminate gracefully
                try:
                    process.wait(timeout=2)
                    logger.debug("Download process terminated gracefully")
                except subprocess.TimeoutExpired:
                    # If it does not terminate in 2 seconds, force termination
                    self.log_message("⚠ Forcing process termination...")
                    logger.warning("Process did not terminate, forcing kill")
                    process.kill()
                    process.wait(timeout=5)
                    logger.info("Download process killed")

                # Clean up partial files
                download.cleanup_partial_files(self)

                self.progress_bar.set_text("Stopped")
                self.progress_bar.set_fraction(0.0)
                self.log_message("✓ Download stopped by user")
            except subprocess.SubprocessError as e:
                logger.error(f"Error stopping download process: {e}")
                self.log_message("✗ Error stopping: {}".format(str(e)))
            except Exception as e:
                logger.error(f"Unexpected error stopping download: {e}")
                self.log_message("✗ Error stopping: {}".format(str(e)))
        else:
            # There is no process yet, but cancellation is requested
            # The thread will detect it and stop
            self.log_message("✓ Cancellation requested")
            self.progress_bar.set_text("Cancelled")
            self.progress_bar.set_fraction(0.0)
            logger.info("Download cancellation requested (no process running)")

    def log_message(self, message):
        """Add a message to the log area. Main-thread only (synchronous)."""
        end_iter = self.log_buffer.get_end_iter()
        self.log_buffer.insert(end_iter, message + "\n")
        # Auto-scroll to the end
        mark = self.log_buffer.create_mark(None, end_iter, False)
        self.log_view.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)

    def queue_log_message(self, message):
        """Thread-safe: enqueue a log line for a batched flush on the main loop.

        Many lines arriving in quick succession (e.g. a large playlist) coalesce
        into a single buffer insert instead of one GLib.idle_add per line.
        """
        with self._log_lock:
            self._log_pending.append(message)
            if self._log_flush_scheduled:
                return
            self._log_flush_scheduled = True
        GLib.idle_add(self._flush_log_queue)

    def _flush_log_queue(self):
        """Drain pending log lines into the buffer in one insert. Main loop only."""
        with self._log_lock:
            pending = self._log_pending
            self._log_pending = []
            self._log_flush_scheduled = False
        if pending:
            end_iter = self.log_buffer.get_end_iter()
            self.log_buffer.insert(end_iter, "\n".join(pending) + "\n")
            end_iter = self.log_buffer.get_end_iter()
            mark = self.log_buffer.create_mark(None, end_iter, False)
            self.log_view.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)
        return False

    def on_download_clicked(self, button):
        """Start download"""
        url = self.url_entry.get_text().strip()

        logger.info("Download button clicked")

        if not url:
            logger.warning("Empty URL provided")
            self.show_error_dialog("Please enter a YouTube URL")
            return

        try:
            url_type, match = utils.classify_youtube_url(url)
        except ValidationError as e:
            logger.error(f"URL validation error: {e}")
            self.show_error_dialog(f"Invalid input:\n{str(e)}")
            return
        except Exception as e:
            logger.error(f"Unexpected error validating URL: {e}")
            self.show_error_dialog(f"Error validating URL:\n{str(e)}")
            return

        if not url_type:
            # Specific error messages depending on the problem
            if "youtube.com" in url or "youtu.be" in url:
                if "/watch?v=" in url and len(re.findall(r'v=([\w-]+)', url)) > 0:
                    video_id = re.findall(r'v=([\w-]+)', url)[0]
                    if len(video_id) != 11:
                        logger.warning(
                            f"Invalid video ID length: {video_id} ({len(video_id)} chars)"
                        )
                        self.show_error_dialog(
                            "Invalid video ID length.\n"
                            "YouTube video IDs must be exactly 11 characters.\n"
                            "Found: {} ({} characters)".format(video_id, len(video_id))
                        )
                        return
                logger.warning(f"Invalid YouTube URL format: {url}")
                self.show_error_dialog(
                    "Invalid YouTube URL format.\n\n"
                    "Valid formats:\n"
                    "• youtube.com/watch?v=VIDEO_ID (11 chars)\n"
                    "• youtu.be/VIDEO_ID\n"
                    "• youtube.com/playlist?list=PLAYLIST_ID\n"
                    "• youtube.com/shorts/VIDEO_ID"
                )
            else:
                logger.warning(f"Not a YouTube URL: {url}")
                self.show_error_dialog(
                    "This doesn't appear to be a YouTube URL.\n"
                    "Please enter a valid YouTube video or playlist URL."
                )
            return

        logger.info(f"Valid {url_type} URL: {url}")

        # Validate and normalize the destination folder
        try:
            download_dir = Path(self.download_path).expanduser().resolve()
            download_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Download directory prepared: {download_dir}")
        except (OSError, PermissionError) as e:
            logger.error(f"Failed to prepare destination folder: {e}")
            self.show_error_dialog("Could not prepare destination folder:\n{}".format(str(e)))
            return
        except Exception as e:
            logger.error(f"Unexpected error with destination folder: {e}")
            self.show_error_dialog("Error with destination folder:\n{}".format(str(e)))
            return

        if not os.access(str(download_dir), os.W_OK | os.X_OK):
            logger.error(f"Destination folder not writable: {download_dir}")
            self.show_error_dialog("Destination folder is not writable:\n{}".format(str(download_dir)))
            return

        self.download_path = str(download_dir)
        self.folder_entry.set_text(self.download_path)

        use_auth = self.use_youtube_auth
        auth_browser = self.config.get('auth_browser', 'firefox')

        # For playlists, show preview dialog to let user select videos
        if url_type == "Playlist":
            self.progress_bar.set_text("Fetching playlist info...")
            self.progress_bar.set_fraction(0.0)
            self._set_ui_sensitive(False)
            self.download_button.set_sensitive(False)

            def fetch_and_preview():
                try:
                    info_cmd = ["yt-dlp", "--flat-playlist", "--print",
                                "%(id)s:::%(playlist_index|)s%(playlist_index& - |)s%(title)s"]
                    if use_auth:
                        info_cmd.extend(["--cookies-from-browser", auth_browser])
                    info_cmd.append(url)

                    result = subprocess.run(info_cmd, capture_output=True, text=True, timeout=60)
                    playlist_info = {}
                    if result.returncode == 0:
                        for line in result.stdout.strip().split('\n'):
                            if ':::' in line:
                                parts = line.split(':::', 1)
                                if len(parts) == 2:
                                    playlist_info[parts[0].strip()] = parts[1].strip()
                    GLib.idle_add(self._show_playlist_preview, url, url_type, use_auth, auth_browser, playlist_info)
                except Exception as e:
                    logger.error(f"Failed to fetch playlist info: {e}")
                    GLib.idle_add(self._show_playlist_preview, url, url_type, use_auth, auth_browser, {})

            threading.Thread(target=fetch_and_preview, daemon=True).start()
            return

        self._start_download(url, url_type, use_auth, auth_browser)

    def _show_playlist_preview(self, url, url_type, use_auth, auth_browser, playlist_info):
        """Show playlist preview dialog after fetching info"""
        self._set_ui_sensitive(True)
        self.download_button.set_sensitive(True)
        self.progress_bar.set_text("Waiting...")

        if not playlist_info:
            # Could not fetch info, proceed with full download
            self.log_message("Could not fetch playlist info, downloading all videos...")
            self._start_download(url, url_type, use_auth, auth_browser)
            return

        dialog = PlaylistPreviewDialog(self, playlist_info)
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            selected = dialog.get_selected_indices()
            dialog.destroy()
            if not selected:
                self.show_error_dialog("No videos selected for download.")
                return
            playlist_items = ",".join(str(i) for i in selected)
            self._start_download(url, url_type, use_auth, auth_browser, playlist_items=playlist_items)
        else:
            dialog.destroy()

    def _start_download(self, url, url_type, use_auth, auth_browser, playlist_items=None):
        """Start the download thread"""
        # Reset download status
        self.download_stopped.clear()
        self.download_cancel_requested.clear()
        self.current_downloading_file = None
        self.current_download_original = None

        # Disable UI elements
        self._set_ui_sensitive(False)

        # Disable download button and enable stop button
        self.download_button.set_sensitive(False)
        self.download_button.get_style_context().remove_class("suggested-action")
        self.stop_button.set_sensitive(True)
        self.stop_button.get_style_context().add_class("destructive-action")
        self.progress_bar.set_text("Downloading...")
        self.progress_bar.set_fraction(0.0)

        # Clear log and hide copy button
        self.log_buffer.set_text("")
        self.copy_log_button.hide()

        self.log_message("Starting download of: {}".format(url))
        self.log_message("Destination: {}".format(self.download_path))
        if playlist_items:
            self.log_message("Selected videos: {}".format(playlist_items))
        self.log_message("-" * 60)
        logger.info(f"Starting download thread for {url_type}")

        # Run download in a separate thread
        try:
            self._download_thread = threading.Thread(
                target=download.download_thread,
                args=(self, url, url_type, self.download_path, use_auth, auth_browser, playlist_items)
            )
            self._download_thread.daemon = True
            self._download_thread.start()
            logger.debug("Download thread started")
        except Exception as e:
            logger.error(f"Failed to start download thread: {e}")
            self.show_error_dialog(f"Could not start download:\n{str(e)}")
            # Restore UI
            self._set_ui_sensitive(True)
            self.download_button.set_sensitive(True)
            self.download_button.get_style_context().add_class("suggested-action")
            self.stop_button.set_sensitive(False)
            self.stop_button.get_style_context().remove_class("destructive-action")

    def show_error_dialog(self, message):
        """Show error dialog"""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            destroy_with_parent=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="Error"
        )
        dialog.format_secondary_text(message)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def show_success_dialog(self, message):
        """Show success dialog"""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            destroy_with_parent=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="Success"
        )
        dialog.format_secondary_text(message)
        dialog.show_all()
        dialog.run()
        dialog.destroy()
