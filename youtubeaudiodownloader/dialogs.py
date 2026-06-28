"""
Dialog windows for YouTube Audio Downloader.

Contains PreferencesDialog and PlaylistPreviewDialog,
extracted from app_window.py for better code organization.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib  # noqa: E402

from . import config  # noqa: E402
from .logger import get_logger  # noqa: E402

if TYPE_CHECKING:
    from .app_window import YouTubeAudioDownloader

logger = get_logger(__name__)


class PreferencesDialog(Gtk.Dialog):
    """Preferences dialog for application settings."""

    def __init__(self, parent: YouTubeAudioDownloader) -> None:
        super().__init__(
            title="Preferences",
            transient_for=parent,
            modal=True,
            destroy_with_parent=True,
        )
        self.set_default_size(400, -1)
        self.set_border_width(10)
        self.parent_window = parent

        content = self.get_content_area()
        content.set_spacing(15)

        # --- Authentication section ---
        auth_frame = Gtk.Frame(label=" Authentication ")
        auth_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        auth_box.set_border_width(10)

        self.auth_checkbox = Gtk.CheckButton(label="Use YouTube authentication (for private playlists)")
        self.auth_checkbox.set_active(parent.use_youtube_auth)
        self.auth_checkbox.set_tooltip_text("Uses browser cookies to access private playlists.")
        self.auth_checkbox.connect("toggled", self._on_auth_toggled)
        auth_box.pack_start(self.auth_checkbox, False, False, 0)

        browser_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        browser_label = Gtk.Label(label="Browser for cookies:")
        browser_label.set_xalign(0)
        browser_box.pack_start(browser_label, False, False, 0)
        self.browser_combo = Gtk.ComboBoxText()
        self.browser_combo.append("firefox", "Firefox")
        self.browser_combo.append("chrome", "Chrome")
        self.browser_combo.append("brave", "Brave")
        self.browser_combo.set_active_id(parent.config.get("auth_browser", "firefox"))
        self.browser_combo.set_sensitive(parent.use_youtube_auth)
        self.browser_combo.connect("changed", self._on_browser_changed)
        browser_box.pack_start(self.browser_combo, False, False, 0)
        auth_box.pack_start(browser_box, False, False, 0)

        auth_frame.add(auth_box)
        content.pack_start(auth_frame, False, False, 0)

        # --- Audio format section ---
        audio_frame = Gtk.Frame(label=" Audio format ")
        audio_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        audio_box.set_border_width(10)

        self.mp3_radio = Gtk.RadioButton.new_with_label_from_widget(
            None, "MP3 320k (re-encoded from source)"
        )
        self.mp3_radio.set_tooltip_text(
            "Converts the source audio to MP3 at 320k. Compatible everywhere."
        )
        audio_box.pack_start(self.mp3_radio, False, False, 0)

        self.opus_radio = Gtk.RadioButton.new_with_label_from_widget(
            self.mp3_radio, "Opus native (no conversion)"
        )
        self.opus_radio.set_tooltip_text(
            "Keeps YouTube's native Opus audio without re-encoding. Best quality, smaller files."
        )
        audio_box.pack_start(self.opus_radio, False, False, 0)

        if parent.audio_format == "opus":
            self.opus_radio.set_active(True)
        else:
            self.mp3_radio.set_active(True)

        # Connect after setting initial state to avoid a spurious save on open
        self.mp3_radio.connect("toggled", self._on_audio_format_toggled)

        # Embed cover art toggle. Disabling it skips yt-dlp's sequential
        # thumbnail probing, which dominates the per-video time on playlists.
        self.thumbnail_checkbox = Gtk.CheckButton(label="Embed cover art (slower)")
        self.thumbnail_checkbox.set_tooltip_text(
            "Embeds the video thumbnail as cover art. Disable for noticeably "
            "faster playlist downloads."
        )
        self.thumbnail_checkbox.set_active(parent.embed_thumbnail)
        self.thumbnail_checkbox.connect("toggled", self._on_embed_thumbnail_toggled)
        audio_box.pack_start(self.thumbnail_checkbox, False, False, 0)

        audio_frame.add(audio_box)
        content.pack_start(audio_frame, False, False, 0)

        # --- Notifications section ---
        notif_frame = Gtk.Frame(label=" Notifications ")
        notif_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        notif_box.set_border_width(10)

        self.notif_checkbox = Gtk.CheckButton(label="Enable desktop notifications")
        self.notif_checkbox.set_active(parent.notifications_enabled)
        self.notif_checkbox.connect("toggled", self._on_notif_toggled)
        notif_box.pack_start(self.notif_checkbox, False, False, 0)

        notif_frame.add(notif_box)
        content.pack_start(notif_frame, False, False, 0)

        # Close button
        self.add_button("Close", Gtk.ResponseType.CLOSE)
        self.connect("response", lambda d, r: d.destroy())
        self.show_all()

    def _on_auth_toggled(self, checkbox: Gtk.CheckButton) -> None:
        try:
            self.parent_window.use_youtube_auth = checkbox.get_active()
            self.browser_combo.set_sensitive(checkbox.get_active())
            self.parent_window.config["use_youtube_auth"] = checkbox.get_active()
            config.save_config(self.parent_window.config)
            logger.info(f"YouTube authentication {'enabled' if checkbox.get_active() else 'disabled'}")
        except Exception as e:
            logger.error(f"Failed to save authentication setting: {e}")

    def _on_browser_changed(self, combo: Gtk.ComboBoxText) -> None:
        try:
            browser = combo.get_active_id()
            self.parent_window.config["auth_browser"] = browser
            config.save_config(self.parent_window.config)
            logger.info(f"Authentication browser changed to: {browser}")
        except Exception as e:
            logger.error(f"Failed to save browser setting: {e}")

    def _on_audio_format_toggled(self, radio: Gtk.RadioButton) -> None:
        try:
            audio_format = "opus" if self.opus_radio.get_active() else "mp3"
            self.parent_window.audio_format = audio_format
            self.parent_window.config["audio_format"] = audio_format
            config.save_config(self.parent_window.config)
            self.parent_window.update_download_button_label()
            logger.info(f"Audio format changed to: {audio_format}")
        except Exception as e:
            logger.error(f"Failed to save audio format setting: {e}")

    def _on_embed_thumbnail_toggled(self, checkbox: Gtk.CheckButton) -> None:
        try:
            self.parent_window.embed_thumbnail = checkbox.get_active()
            self.parent_window.config["embed_thumbnail"] = checkbox.get_active()
            config.save_config(self.parent_window.config)
            logger.info(f"Embed cover art {'enabled' if checkbox.get_active() else 'disabled'}")
        except Exception as e:
            logger.error(f"Failed to save embed thumbnail setting: {e}")

    def _on_notif_toggled(self, checkbox: Gtk.CheckButton) -> None:
        try:
            self.parent_window.notifications_enabled = checkbox.get_active()
            self.parent_window.config["notifications_enabled"] = checkbox.get_active()
            config.save_config(self.parent_window.config)
            # Update the app action state
            app = self.parent_window.get_application()
            if app:
                action = app.lookup_action("toggle-notifications")
                if action:
                    action.set_state(GLib.Variant.new_boolean(checkbox.get_active()))
            logger.info(f"Notifications {'enabled' if checkbox.get_active() else 'disabled'}")
        except Exception as e:
            logger.error(f"Failed to save notification setting: {e}")


class PlaylistPreviewDialog(Gtk.Dialog):
    """Dialog to preview and select videos from a playlist before downloading."""

    def __init__(self, parent: YouTubeAudioDownloader, playlist_info: Dict[str, str]) -> None:
        super().__init__(
            title="Playlist Preview",
            transient_for=parent,
            modal=True,
            destroy_with_parent=True,
        )
        self.set_default_size(500, 400)
        self.set_border_width(10)

        content = self.get_content_area()
        content.set_spacing(10)

        # Header
        header = Gtk.Label()
        header.set_markup("<b>{} videos found in playlist</b>".format(len(playlist_info)))
        header.set_xalign(0)
        content.pack_start(header, False, False, 0)

        # Select all / Deselect all buttons
        select_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        select_all_btn = Gtk.Button(label="Select All")
        select_all_btn.connect("clicked", self._on_select_all)
        deselect_all_btn = Gtk.Button(label="Deselect All")
        deselect_all_btn.connect("clicked", self._on_deselect_all)
        select_box.pack_start(select_all_btn, False, False, 0)
        select_box.pack_start(deselect_all_btn, False, False, 0)
        content.pack_start(select_box, False, False, 0)

        # Scrollable list of checkboxes
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        listbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        self.checkboxes: List[Gtk.CheckButton] = []
        for video_id, title in playlist_info.items():
            cb = Gtk.CheckButton(label=title)
            cb.set_active(True)
            cb.video_id = video_id  # type: ignore[attr-defined]
            self.checkboxes.append(cb)
            listbox.pack_start(cb, False, False, 0)

        scrolled.add(listbox)
        content.pack_start(scrolled, True, True, 0)

        # Selection count label
        self.count_label = Gtk.Label()
        self._update_count()
        content.pack_start(self.count_label, False, False, 0)

        # Connect toggles to update count
        for cb in self.checkboxes:
            cb.connect("toggled", lambda w: self._update_count())

        # Buttons
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        download_btn = self.add_button("Download Selected", Gtk.ResponseType.OK)
        download_btn.get_style_context().add_class("suggested-action")

        self.show_all()

    def _update_count(self) -> None:
        selected = sum(1 for cb in self.checkboxes if cb.get_active())
        self.count_label.set_text("{} of {} selected".format(selected, len(self.checkboxes)))

    def _on_select_all(self, button: Gtk.Button) -> None:
        for cb in self.checkboxes:
            cb.set_active(True)

    def _on_deselect_all(self, button: Gtk.Button) -> None:
        for cb in self.checkboxes:
            cb.set_active(False)

    def get_selected_indices(self) -> List[int]:
        """Return 1-based indices of selected videos."""
        return [i + 1 for i, cb in enumerate(self.checkboxes) if cb.get_active()]
