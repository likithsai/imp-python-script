#!/usr/bin/env python3
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from constants.constant import Constants

class VideoConverter:
    def __init__(self, folder: Path):
        self.folder = folder.expanduser().resolve()
        self.total_saved_mb = 0.0
        self.skipped_count = 0
        self.start_time = time.time()

    # ---------------- Helpers ----------------
    @staticmethod
    def format_time(seconds: float) -> str:
        mins, secs = divmod(int(seconds), 60)
        return f"{mins}m {secs}s"

    def print_progress(self, current: float, total: float, prefix: str = "") -> None:
        percent = f"{100 * (current / total):.1f}"
        filled = int(Constants.PROGRESS_BAR_LENGTH * current // total)
        bar = "█" * filled + "-" * (Constants.PROGRESS_BAR_LENGTH - filled)
        sys.stdout.write(f"\r{Constants.CLR}{prefix} |{bar}| {percent}%")
        sys.stdout.flush()

    @staticmethod
    def format_size(size_mb: float) -> str:
        size_bytes = size_mb * 1024 * 1024
        if size_bytes <= 0:
            return "0 B"
        units = ("B", "KB", "MB", "GB", "TB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        return f"{round(size_bytes / p, 2)} {units[i]}"

    @staticmethod
    def truncate_filename(name: str) -> str:
        max_len = Constants.TRUNCATE_FILENAME_LENGTH
        truncated = name if len(name) <= max_len else name[: max_len - 3] + "..."
        return truncated.ljust(max_len)

    @staticmethod
    def time_to_seconds(time_str: str) -> float:
        try:
            h, m, s = time_str.split(":")
            return float(h) * 3600 + float(m) * 60 + float(s)
        except ValueError:
            return 0.0

    # ---------------- FFmpeg & Metadata ----------------
    def check_video_metadata(self, video: Path):
        """Worker function for multi-threaded scanning."""
        try:
            res = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-show_entries",
                    f"format_tags={Constants.META_TAG_KEY}",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(video),
                ],
                capture_output=True,
                text=True,
                timeout=5
            )
            # If the tag doesn't match our 'optimized' value, we need to process it
            if res.stdout.strip() != Constants.META_VALUE:
                return video
        except Exception:
            return video
        return None

    def update_metadata_only(self, video_path: Path) -> None:
        temp_meta = video_path.with_suffix(".meta.mp4")
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-i",
            str(video_path),
            "-c",
            "copy",
            "-metadata",
            f"{Constants.META_TAG_KEY}={Constants.META_VALUE}",
            str(temp_meta),
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            temp_meta.replace(video_path)
        except subprocess.SubprocessError:
            temp_meta.unlink(missing_ok=True)

    @staticmethod
    def get_duration(video_path: Path) -> float:
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "csv=p=0",
                    str(video_path),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    def convert_video(self, video_path: Path, index: int, total: int) -> None:
        display_name = self.truncate_filename(video_path.name)
        duration = self.get_duration(video_path)
        original_size = video_path.stat().st_size / (1024 * 1024)
        prefix = f"[{index}/{total}] {display_name}"

        if duration <= 0:
            print(f"\r{Constants.CLR}{prefix} | {Constants.RED}FAIL (No Duration){Constants.RESET}")
            return

        # FIX: Use a fixed, short temporary name in the same directory
        # This prevents "File name too long" errors
        temp_path = video_path.parent / f"temp_proc_{index}.mp4"
        
        cmd = [
            "ffmpeg", "-hide_banner", "-i", str(video_path),
            "-c:v", Constants.VIDEO_CODEC, "-preset", Constants.PRESET, "-crf", Constants.CRF,
            "-c:a", Constants.AUDIO_CODEC, "-b:a", Constants.AUDIO_BITRATE,
            "-movflags", "+faststart", "-metadata", f"{Constants.META_TAG_KEY}={Constants.META_VALUE}",
            "-y", str(temp_path),
        ]

        try:
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True)
            for line in process.stderr:
                if "time=" in line:
                    t = next((p.split("=")[1] for p in line.split() if p.startswith("time=")), "00:00:00")
                    self.print_progress(self.time_to_seconds(t), duration, prefix)

            process.wait()

            if process.returncode == 0:
                new_size = temp_path.stat().st_size / (1024 * 1024)
                if new_size < original_size:
                    # Keep original extension but swap files
                    backup = video_path.with_suffix(".bak")
                    video_path.rename(backup)
                    temp_path.rename(video_path) # Move short temp to original long name
                    backup.unlink()
                    self.total_saved_mb += original_size - new_size
                    status = f"{Constants.GREEN}DONE{Constants.RESET} ({self.format_size(original_size)} → {self.format_size(new_size)})"
                else:
                    temp_path.unlink()
                    self.update_metadata_only(video_path)
                    self.skipped_count += 1
                    status = f"{Constants.YELLOW}SKIP{Constants.RESET} ({self.format_size(original_size)} → {self.format_size(new_size)})"
            else:
                status = f"{Constants.RED}FAIL{Constants.RESET}"

            print(f"\r{Constants.CLR}{prefix} | {status}")
        except Exception as e:
            print(f"\r{Constants.CLR}{prefix} | {Constants.RED}ERROR: {str(e)[:50]}{Constants.RESET}")
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
                
    # ---------------- Main Logic ----------------
    def process_folder(self) -> None:
        try:
            # Filter: ignore hidden files (starts with .) and macOS metadata (._)
            videos = [
                p for p in self.folder.rglob("*")
                if p.is_file() 
                and p.suffix.lower() in Constants.VIDEO_EXTENSIONS
                and not p.name.startswith(".")
            ]

            if not videos:
                print(f"{Constants.YELLOW}No videos found in {self.folder}{Constants.RESET}")
                return

            print(f"🔎 Scanning {len(videos)} files")
            to_process = []

            with ThreadPoolExecutor() as executor:
                for i, result in enumerate(executor.map(self.check_video_metadata, videos), 1):
                    if result:
                        to_process.append(result)
                    self.print_progress(i, len(videos), "Scanning for Metadata")

            print(f"\n🚀 Found {len(to_process)} videos to optimize\n")

            for idx, video in enumerate(to_process, start=1):
                self.convert_video(video, idx, len(to_process))

            print(f"\n{Constants.CYAN}Summary{Constants.RESET}")
            print(f"✨ Total Saved : {self.format_size(self.total_saved_mb)}")
            print(f"⏩ Skipped     : {self.skipped_count}")
            print(f"⏱️  Time Taken : {self.format_time(time.time() - self.start_time)}\n")

        except KeyboardInterrupt:
            print(f"\n\n{Constants.RED}Terminated by user. Exiting...{Constants.RESET}")
            sys.exit(0)

def main() -> None:
    print(f"{Constants.CYAN}🎬 Video Optimizer v1.0{Constants.RESET}\n")
    if len(sys.argv) < 2:
        print("Usage: python3 script.py /path/to/videos")
        sys.exit(1)
    if not shutil.which("ffmpeg"):
        sys.exit("❌ Error: ffmpeg is not installed.")
    
    VideoConverter(Path(sys.argv[1])).process_folder()

if __name__ == "__main__":
    main()