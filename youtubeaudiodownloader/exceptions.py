"""
Custom exception classes for YouTube Audio Downloader.

This module defines specific exception types for better error categorization
and handling throughout the application.
"""


class YouTubeAudioDownloaderError(Exception):
    """Base exception for all YouTube Audio Downloader errors."""
    pass


class ConfigurationError(YouTubeAudioDownloaderError):
    """Exception raised for configuration loading/saving issues."""
    pass


class DependencyError(YouTubeAudioDownloaderError):
    """Exception raised when required dependencies are missing."""

    def __init__(self, missing_deps: "list[str] | str") -> None:
        if isinstance(missing_deps, str):
            missing_deps = [missing_deps]
        self.missing_deps: list[str] = missing_deps
        deps_str = ", ".join(missing_deps)
        super().__init__(f"Missing required dependencies: {deps_str}")


class DownloadError(YouTubeAudioDownloaderError):
    """Exception raised when download operations fail."""
    pass


class ValidationError(YouTubeAudioDownloaderError):
    """Exception raised for invalid URLs, paths, or other validation failures."""
    pass
