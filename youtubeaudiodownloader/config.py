
from __future__ import annotations

import json
from typing import Any, Dict
from pathlib import Path

from .exceptions import ConfigurationError
from .logger import get_logger

logger = get_logger(__name__)

# Configuration file location
CONFIG_DIR = Path.home() / ".config" / "youtube-audio-downloader"
CONFIG_FILE = CONFIG_DIR / "config.json"
# Migrate config from the previous "youtube-mp3-downloader" location on first load.
LEGACY_CONFIG_FILE = Path.home() / ".config" / "youtube-mp3-downloader" / "config.json"

# Supported audio output formats. "mp3" is re-encoded at 320k; "opus" is the
# native YouTube stream copied without conversion.
VALID_AUDIO_FORMATS = ("mp3", "opus")
DEFAULT_AUDIO_FORMAT = "mp3"


def _validate_config(config: Any) -> Dict[str, Any]:
    """
    Validate the configuration structure.

    Args:
        config: Configuration dictionary to validate

    Returns:
        Validated configuration dictionary
    """
    if not isinstance(config, dict):
        logger.warning("Config is not a dictionary, using empty config")
        return {}

    # Ensure expected types for known keys
    validated = {}
    for key, value in config.items():
        validated[key] = value

    # Normalize audio_format to a supported value, falling back to the default
    audio_format = validated.get("audio_format")
    if audio_format is not None and audio_format not in VALID_AUDIO_FORMATS:
        logger.warning(
            f"Unknown audio_format '{audio_format}', falling back to '{DEFAULT_AUDIO_FORMAT}'"
        )
        validated["audio_format"] = DEFAULT_AUDIO_FORMAT

    logger.debug(f"Configuration validated with {len(validated)} keys")
    return validated


def load_config() -> Dict[str, Any]:
    """
    Load configuration from JSON file.

    Returns:
        Configuration dictionary (empty dict if not found or invalid)
    """
    logger.debug("Loading configuration...")

    # Create config directory if it doesn't exist
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Config directory ready: {CONFIG_DIR}")
    except (OSError, PermissionError) as e:
        logger.error(f"Failed to create config directory {CONFIG_DIR}: {e}")
        return {}

    # Check for legacy config file and migrate
    if LEGACY_CONFIG_FILE.exists() and not CONFIG_FILE.exists():
        try:
            import shutil
            logger.info(f"Migrating legacy config from {LEGACY_CONFIG_FILE}")
            shutil.move(str(LEGACY_CONFIG_FILE), str(CONFIG_FILE))
            logger.info("Legacy config migrated successfully")
        except (OSError, PermissionError, IOError) as e:
            logger.warning(f"Could not migrate legacy config: {e}")

    # Load config
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                logger.info("Configuration loaded successfully")
                return _validate_config(config_data)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse config file {CONFIG_FILE}: {e}")
            logger.warning("Using default configuration")
        except (IOError, OSError) as e:
            logger.error(f"Failed to read config file {CONFIG_FILE}: {e}")
            logger.warning("Using default configuration")
        except PermissionError as e:
            logger.error(f"Permission denied reading config file {CONFIG_FILE}: {e}")
            logger.warning("Using default configuration")
    else:
        logger.debug(f"Config file not found: {CONFIG_FILE}, using defaults")

    # Return default config
    return {}


def save_config(config: Dict[str, Any]) -> None:
    """
    Save configuration to JSON file.

    Args:
        config: Configuration dictionary to save

    Raises:
        ConfigurationError: If the configuration cannot be saved
    """
    logger.debug("Saving configuration...")

    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError) as e:
        logger.error(f"Failed to create config directory {CONFIG_DIR}: {e}")
        raise ConfigurationError(f"Cannot create config directory: {e}") from e

    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        logger.info(f"Configuration saved successfully to {CONFIG_FILE}")
    except (IOError, OSError) as e:
        logger.error(f"Failed to write config file {CONFIG_FILE}: {e}")
        raise ConfigurationError(f"Cannot write config file: {e}") from e
    except PermissionError as e:
        logger.error(f"Permission denied writing config file {CONFIG_FILE}: {e}")
        raise ConfigurationError(f"Permission denied: {e}") from e
    except TypeError as e:
        logger.error(f"Invalid config data structure: {e}")
        raise ConfigurationError(f"Invalid config data: {e}") from e
