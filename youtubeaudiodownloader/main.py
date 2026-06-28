import sys
import shutil

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gio  # noqa: E402

from .app_window import YouTubeAudioDownloader  # noqa: E402
from .dialogs import PreferencesDialog  # noqa: E402
from . import config  # noqa: E402
from .exceptions import DependencyError  # noqa: E402
from .logger import get_logger  # noqa: E402

logger = get_logger(__name__)


def check_dependencies() -> bool:
    """
    Check for required command-line tools.

    Raises:
        DependencyError: If required dependencies are missing
    """
    logger.info("Checking dependencies...")

    # Check required dependencies
    missing_deps = []
    if not shutil.which("yt-dlp"):
        logger.error("yt-dlp not found in PATH")
        missing_deps.append("yt-dlp")
    if not shutil.which("ffmpeg"):
        logger.error("ffmpeg not found in PATH")
        missing_deps.append("ffmpeg")

    if missing_deps:
        logger.critical(f"Missing required dependencies: {', '.join(missing_deps)}")

        # Show error dialog
        try:
            dialog = Gtk.MessageDialog(
                transient_for=None,
                modal=True,
                destroy_with_parent=True,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="Missing Dependencies"
            )
            missing_str = "\n".join(missing_deps)
            dialog.format_secondary_text(
                "The following required tools are not installed or not in your PATH:\n\n"
                f"{missing_str}\n\n"
                "Please install them to continue."
            )
            dialog.run()
            dialog.destroy()
        except Exception as e:
            logger.error(f"Failed to show dependency error dialog: {e}")

        raise DependencyError(missing_deps)

    # Check optional dependencies and warn if missing
    optional_deps = []
    if not shutil.which("notify-send"):
        logger.warning("notify-send not found - notifications may not work")
        optional_deps.append("notify-send")
    if not shutil.which("xdg-open"):
        logger.warning("xdg-open not found - opening folders may not work")
        optional_deps.append("xdg-open")

    if optional_deps:
        logger.info(f"Optional dependencies missing (non-critical): {', '.join(optional_deps)}")

    logger.info("All required dependencies found")
    return True


class Application(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.github.sebasalas.youtube-audio-downloader")
        self.window = None

    def do_activate(self):
        """Activate the application and create the main window."""
        try:
            if not self.window:
                logger.info("Creating application window...")
                self.window = YouTubeAudioDownloader()
                self.window.set_application(self)
                self.add_window(self.window)

                # Action for toggling notifications (state tracked for preferences dialog)
                try:
                    toggle_notifications_action = Gio.SimpleAction.new_stateful(
                        "toggle-notifications",
                        None,
                        GLib.Variant.new_boolean(self.window.notifications_enabled)
                    )
                    toggle_notifications_action.connect("activate", self.on_toggle_notifications)
                    self.add_action(toggle_notifications_action)
                    logger.debug("Notification toggle action registered")
                except Exception as e:
                    logger.error(f"Failed to register notification action: {e}")

                # Action for showing preferences dialog
                try:
                    prefs_action = Gio.SimpleAction.new("show-preferences", None)
                    prefs_action.connect("activate", self.on_show_preferences)
                    self.add_action(prefs_action)
                    logger.debug("Preferences action registered")
                except Exception as e:
                    logger.error(f"Failed to register preferences action: {e}")

            self.window.show_all()
            logger.info("Application window shown")
        except Exception as e:
            logger.critical(f"Failed to activate application: {e}", exc_info=True)
            # Show error dialog if possible
            try:
                dialog = Gtk.MessageDialog(
                    transient_for=None,
                    modal=True,
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text="Application Error"
                )
                dialog.format_secondary_text(
                    f"Failed to start the application:\n\n{str(e)}"
                )
                dialog.run()
                dialog.destroy()
            except Exception as dialog_error:
                # If we can't even show the error dialog, just log it
                logger.error(f"Failed to show error dialog: {dialog_error}")
            raise

    def on_show_preferences(self, action, parameter):
        """Show the preferences dialog"""
        try:
            PreferencesDialog(self.window)
        except Exception as e:
            logger.error(f"Failed to show preferences dialog: {e}")

    def on_toggle_notifications(self, action, parameter):
        """Handle notification toggle"""
        try:
            # Change the state
            current_state = action.get_state().get_boolean()
            new_state = not current_state
            action.set_state(GLib.Variant.new_boolean(new_state))

            # Update in the window
            self.window.notifications_enabled = new_state

            # Save to configuration
            self.window.config['notifications_enabled'] = new_state
            config.save_config(self.window.config)
            logger.info(f"Notifications {'enabled' if new_state else 'disabled'}")
        except Exception as e:
            logger.error(f"Failed to toggle notifications: {e}")


def main() -> int:
    """Main entry point for the application."""
    logger.info("YouTube Audio Downloader starting...")

    try:
        # Check dependencies before starting the app
        check_dependencies()
    except DependencyError:
        logger.critical("Cannot start application due to missing dependencies")
        return 1

    try:
        app = Application()
        return int(app.run(sys.argv))
    except Exception as e:
        logger.critical(f"Application crashed: {e}", exc_info=True)
        return 1
