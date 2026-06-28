# YouTube Audio Downloader

A GTK 3 desktop application for downloading YouTube videos and playlists as audio.
Paste a link, pick a destination, and get your audio for offline listening.

Built on [yt-dlp](https://github.com/yt-dlp/yt-dlp) and [ffmpeg](https://ffmpeg.org/),
with a clean single-window interface.

## Features

- **Two audio formats:** MP3 at 320k (re-encoded, compatible everywhere) or native
  Opus (no re-encoding, best quality and smaller files since YouTube already serves Opus).
- **Videos and playlists:** Download a single video or an entire playlist.
- **Playlist preview:** See every video in a playlist and choose which ones to download
  before starting.
- **Metadata and cover art:** Embeds metadata into every file and, optionally, the video
  thumbnail as cover art. Cover art is on by default but can be disabled in Preferences for
  noticeably faster playlist downloads.
- **Private and unlisted content:** Authenticate using cookies from your browser
  (Firefox, Chrome, or Brave) to access content that isn't public.
- **Live progress:** Progress bar with real-time download speed and ETA, plus a scrolling log.
- **Duplicate detection:** Warns you before overwriting an existing file.
- **Resilient playlists:** Keeps going if one video fails and reports failures and skips
  at the end.
- **Desktop notifications:** Notifies you when a download finishes (with a `notify-send`
  fallback).
- **Cancellable downloads:** A stop button terminates the download and cleans up partial files.

## Requirements

System packages: `python3`, `python-gobject`, `gtk3`, `yt-dlp`, `ffmpeg`.

PyGObject must come from your system package manager, not pip, because it links
against the system GTK libraries.

## Installation (Linux)

### 1. Install dependencies

**Arch Linux**

```bash
sudo pacman -S python python-gobject gtk3 yt-dlp ffmpeg
```

**Debian / Ubuntu**

```bash
sudo apt install python3 python3-gi gir1.2-gtk-3.0 yt-dlp ffmpeg
```

### 2. Install the app

Clone the repository, then either install it system-wide:

```bash
sudo ./install.sh
```

This adds "YouTube Audio Downloader" to your application menu. Remove it with
`sudo ./uninstall.sh`.

Or run it directly without installing:

```bash
./youtube_audio_downloader.py
```

## Usage

1. Open the app and paste a YouTube video or playlist URL.
2. Choose the destination folder.
3. Click the download button (its label reflects the selected format — MP3 or Opus).
4. For playlists, a preview dialog lets you select which videos to download.
5. Watch progress in the log and progress bar; use the stop button to cancel.

### Private or unlisted content

1. Open **Preferences** from the hamburger menu.
2. Enable **YouTube authentication** and pick the browser you're signed into.
3. Make sure you're logged into YouTube in that browser, then start the download.

### Choosing the audio format

Open **Preferences** and pick between **MP3 320k** and **Opus native** under
"Audio format". The choice is saved and applied to subsequent downloads.

### Cover art and speed

Cover art embedding is enabled by default. Turning off **Embed cover art** in Preferences
skips yt-dlp's thumbnail probing, which is the slowest step per video on playlists — useful
when you want speed over embedded artwork.

## Configuration

Preferences (last folder, window size, authentication, audio format, cover art,
notifications) are stored in `~/.config/youtube-audio-downloader/config.json`. Delete
that file to reset to defaults.

Logs are written to `~/.config/youtube-audio-downloader/app.log` (rotating, DEBUG level).

## Development

### Project layout

```
youtube-audio-downloader/
├── youtube_audio_downloader.py     # Entry-point script
├── pyproject.toml                # Packaging, pytest, mypy, black, flake8 config
├── youtubeaudiodownloader/         # Application package
│   ├── main.py                   # Application lifecycle, dependency checks
│   ├── app_window.py             # Main window, UI layout and event handlers
│   ├── dialogs.py                # Preferences and playlist preview dialogs
│   ├── download.py               # yt-dlp command building, streaming, cleanup
│   ├── parsing.py                # Pure parsers for yt-dlp structured output
│   ├── config.py                 # JSON config with legacy-path migration
│   ├── exceptions.py             # Custom exception hierarchy
│   ├── logger.py                 # Console + rotating file logging
│   └── utils.py                  # URL validation and classification
├── tests/                        # pytest suite (config, utils, parsing, download)
├── data/                         # Application and download icons
├── install.sh / uninstall.sh     # System-wide install scripts
└── .github/workflows/ci.yml      # CI: flake8, mypy, pytest
```

### Architecture

Downloads run in daemon threads that spawn yt-dlp via `subprocess.Popen`, parse its
structured output line by line, and marshal every UI update back to the GTK main loop
via `GLib.idle_add()`. GTK methods are never called from worker threads. Cancellation
uses `threading.Event` flags, and a `threading.Lock` guards shared download state.

### Running tests

```bash
python3 -m pytest tests/ -v
```

## Credits

- Application icon from the [Tela Circle Icon Theme](https://github.com/vinceliuice/Tela-circle-icon-theme)
  by [vinceliuice](https://github.com/vinceliuice), licensed under
  [GPLv3](https://github.com/vinceliuice/Tela-circle-icon-theme/blob/master/COPYING).

## License

MIT
