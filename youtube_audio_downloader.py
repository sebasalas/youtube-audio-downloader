#!/usr/bin/env python3
"""
YouTube Audio Downloader - GTK GUI Application
Download individual videos or complete YouTube playlists
and converts them to 320kbps CBR MP3 using yt-dlp + FFmpeg
"""

import sys
from youtubeaudiodownloader.main import main

if __name__ == "__main__":
    sys.exit(main())