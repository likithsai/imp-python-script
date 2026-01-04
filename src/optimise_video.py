#!/usr/bin/env python3
import subprocess
import sys
import shutil
import time
import math
from pathlib import Path
from typing import Set

class VideoConverter:
    # ---------------- Configuration ----------------
    VIDEO_EXTENSIONS: Set[str] = {
        ".avi", ".mkv", ".mov", ".flv", ".wmv", ".webm", ".m4v",
        ".ts", ".mpg", ".mpeg", ".3gp", ".mp4", ".ogg"
    }

    META_TAG_KEY: str = "comment"
    META_VALUE: str = "video_converter_v2"

    # Colors and ANSI
    CLR = "\033[K"   # Clear line from cursor to end
    UP = "\033[F"    # Move cursor up one line
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    RESET = "\033[0m"

    def __init__(self, folder: Path):
        self.folder = folder.expanduser().resolve()
        self.total_saved_mb = 0.0
        self.skipped_count = 0
        self.start_time = time.time()

    # ---------------- UI Helpers ----------------
    def format_time(self, seconds: float) -> str:
        mins, secs = divmod(int(seconds), 60)
        return f"{mins}m {secs}s"

    def print_progress(self, current, total, prefix='', length=20):
        percent = f"{100 * (current / float(total)):.1f}"
        filled = int(length * current // total)
        bar = '█' * filled + '-' * (length - filled)
        sys.stdout.write(f'\r{self.CLR}{prefix} | |{bar}| {percent}%')
        sys.stdout.flush()

    def format_size(self, size_mb: float) -> str:
        size_bytes = size_mb * 1024 * 1024
        if size_bytes <= 0: return "0 B"
        units = ("B", "KB", "MB", "GB", "TB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        return f"{round(size_bytes / p, 2)} {units[i]}"

    @staticmethod
    def truncate_filename(name: str, max_length: int = 35) -> str:
        truncated = name if len(name) <= max_length else name[: max_length - 3] + "..."
        return truncated.ljust(max_length)

    @staticmethod
    def time_to_seconds(time_str: str) -> float:
        try:
            parts = time_str.split(":")
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        except: return 0.0

    # ---------------- Logic ----------------
    def update_metadata_only(self, video_path: Path):
        temp_meta = video_path.with_name(f"{video_path.stem}.meta.mp4")
        cmd = ["ffmpeg", "-hide_banner", "-y", "-i", str(video_path), "-c", "copy",
               "-metadata", f"{self.META_TAG_KEY}={self.META_VALUE}", str(temp_meta)]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            temp_meta.replace(video_path)
        except:
            if temp_meta.exists(): temp_meta.unlink()

    def get_duration(self, video_path: Path) -> float:
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video_path)],
                capture_output=True, text=True, check=True
            )
            return float(result.stdout.strip())
        except: return 0.0

    def convert_video(self, video_path: Path, index: int, total: int):
        display_name = self.truncate_filename(video_path.name)
        duration = self.get_duration(video_path)
        original_size = video_path.stat().st_size / (1024 * 1024)
        row_prefix = f"[{index}/{total}] {display_name}"

        if duration <= 0:
            print(f"\r{self.CLR}{row_prefix} | {self.RED}FAIL (No duration){self.RESET}")
            return

        temp_path = video_path.with_name(f"{video_path.stem}.temp.mp4")
        cmd = [
                "ffmpeg", 
                "-hide_banner",
                "-i", 
                str(video_path), 
                "-c:v", 
                "libx264", 
                "-preset", 
                "medium", 
                "-crf", 
                "28", 
                "-c:a", 
                "aac", 
                "-b:a", 
                "128k", 
                "-movflags", 
                "+faststart",
                "-metadata", 
                f"{self.META_TAG_KEY}={self.META_VALUE}", 
                "-y", 
                str(temp_path)
            ]

        try:
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True, bufsize=1)
            for line in process.stderr:
                if "time=" in line:
                    t_match = next((p for p in line.split() if p.startswith("time=")), "time=00:00:00").split('=')[1]
                    curr_sec = self.time_to_seconds(t_match)
                    self.print_progress(curr_sec, duration, prefix=row_prefix)

            process.wait()
            
            if process.returncode == 0:
                new_size = temp_path.stat().st_size / (1024 * 1024)
                if new_size < original_size:
                    video_path.rename(video_path.with_suffix(".mp4.bak"))
                    temp_path.rename(video_path.with_suffix(".mp4"))
                    video_path.with_suffix(".mp4.bak").unlink()
                    self.total_saved_mb += (original_size - new_size)
                    status = f"{self.GREEN}DONE{self.RESET} ({self.format_size(original_size)} → {self.format_size(new_size)})"
                else:
                    temp_path.unlink()
                    self.update_metadata_only(video_path)
                    self.skipped_count += 1
                    status = f"{self.YELLOW}SKIP{self.RESET} ({self.format_size(original_size)} → {self.format_size(new_size)})"
            else:
                status = f"{self.RED}FAIL (FFmpeg Error){self.RESET}"

            print(f"\r{self.CLR}{row_prefix} | {status}")

        except KeyboardInterrupt:
            if temp_path.exists(): temp_path.unlink()
            sys.exit(0)
        finally:
            if temp_path.exists(): temp_path.unlink()

    def process_folder(self):
        videos = [p for p in self.folder.rglob("*") if p.is_file() and p.suffix.lower() in self.VIDEO_EXTENSIONS]
        if not videos: return

        # Start scanning
        sys.stdout.write(f"🔎 Scanning {len(videos)} files...\n")
        to_process = []
        for i, v in enumerate(videos):
            name = self.truncate_filename(v.name)
            self.print_progress(i + 1, len(videos), prefix=f"Checking {name}")
            try:
                res = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", f"format_tags={self.META_TAG_KEY}",
                     "-of", "default=noprint_wrappers=1:nokey=1", str(v)],
                    capture_output=True, text=True
                )
                if res.stdout.strip() != self.META_VALUE:
                    to_process.append(v)
            except:
                to_process.append(v)
        
        # --- CLEAN UP SCANNING TEXT ---
        # Move up two lines (Scanning line and the progress bar line) and clear them
        sys.stdout.write(f"\r{self.CLR}{self.UP}{self.CLR}")
        sys.stdout.flush()

        print(f"\n🚀 Found {len(to_process)} videos to optimize{'\n' if len(to_process) > 0 else ''}")
        for idx, video in enumerate(to_process, start=1):
            self.convert_video(video, idx, len(to_process))

        print(f"\n{self.CYAN}Summary\t:{self.RESET}")
        print(f"✨ Total Saved\t: {self.format_size(self.total_saved_mb)}")
        print(f"⏩ Skipped\t: {self.skipped_count}")
        print(f"⏱️  Time Taken\t: {self.format_time(time.time() - self.start_time)}\n")

def main():
    print(f"{VideoConverter.CYAN}🎬 Video Converter v2.3{VideoConverter.RESET}")
    if len(sys.argv) < 2: sys.exit(1)
    if not shutil.which("ffmpeg"): sys.exit("❌ Error: ffmpeg is not installed.")
    VideoConverter(Path(sys.argv[1])).process_folder()

if __name__ == "__main__":
    main()