from typing import Set


class Constants:
    # ---------------- Video ----------------
    VIDEO_EXTENSIONS: Set[str] = {
        ".avi",
        ".mkv",
        ".mov",
        ".flv",
        ".wmv",
        ".webm",
        ".m4v",
        ".ts",
        ".mpg",
        ".mpeg",
        ".3gp",
        ".mp4",
        ".ogg",
    }

    META_TAG_KEY = "comment"
    META_VALUE = "video_converter_v2"

    # ---------------- FFmpeg ----------------
    VIDEO_CODEC = "libx264"
    AUDIO_CODEC = "aac"
    AUDIO_BITRATE = "128k"
    PRESET = "medium"
    CRF = "28"

    # ---------------- UI ----------------
    PROGRESS_BAR_LENGTH = 20
    TRUNCATE_FILENAME_LENGTH = 35

    # ---------------- ANSI ----------------
    CLR = "\033[K"
    UP = "\033[F"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    RESET = "\033[0m"