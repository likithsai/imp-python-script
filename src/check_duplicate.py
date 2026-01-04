#!/usr/bin/env python3
import hashlib
import os
import argparse
import sys
import logging
import signal
import time
from pathlib import Path
from collections import defaultdict

# ---------------- Signal Handling ----------------
def signal_handler(sig, frame):
    print("\n🛑 Interrupted by user. Exiting safely...")
    logging.warning("Process interrupted by user.")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# ---------------- Logging ----------------
LOG_FILE = "duplicate_finder.log"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    filemode="w"
)

# ---------------- Duplicate Manager ----------------
class DuplicateManager:
    def __init__(self, target_dir: str, delete: bool = False):
        self.target_dir = Path(target_dir).expanduser().resolve()
        self.delete = delete
        self.size_map = defaultdict(list)
        self.hash_map = defaultdict(list)
        self.total_scanned = 0
        self.wasted_space_bytes = 0
        self.start_time = None

    # ---------- Utilities ----------
    def _terminal_width(self) -> int:
        try:
            return os.get_terminal_size().columns
        except OSError:
            return 80

    def format_size(self, size: int) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} PB"

    def format_eta(self, seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}s"
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{int(h)}h {int(m)}m" if h else f"{int(m)}m {int(s)}s"

    # ---------- Hashing ----------
    def get_file_hash(self, file_path: Path, block_size: int = 2 * 1024 * 1024):
        sha = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(block_size), b""):
                    sha.update(chunk)
            return sha.hexdigest()
        except (PermissionError, OSError) as e:
            logging.error(f"Read failed: {file_path} | {e}")
            return None

    # ---------- Progress ----------
    def update_progress(self, current: int, total: int, file_path: Path):
        elapsed = time.time() - self.start_time
        rate = current / elapsed if elapsed else 0
        eta = (total - current) / rate if rate else 0

        width = self._terminal_width()
        bar_width = min(30, width - 50)
        percent = (current / total) * 100
        filled = int(bar_width * percent / 100)
        bar = "█" * filled + "-" * (bar_width - filled)

        try:
            size = self.format_size(file_path.stat().st_size)
        except OSError:
            size = "N/A"

        name_display = file_path.name[: width - 50]

        sys.stdout.write(
            f"\r|{bar}| {percent:5.1f}% "
            f"({current}/{total}) ETA {self.format_eta(eta)}  "
            f"{name_display} [{size}]\033[K"
        )
        sys.stdout.flush()

    # ---------- Main ----------
    def run(self):
        if not self.target_dir.is_dir():
            print(f"❌ Invalid directory: {self.target_dir}")
            return

        print(f"📂 Scanning: {self.target_dir}")
        self.start_time = time.time()

        # -------- Pass 1: Group by file size --------
        for root, _, files in os.walk(self.target_dir, followlinks=False):
            for name in files:
                path = Path(root) / name
                try:
                    if not path.is_symlink():
                        self.size_map[path.stat().st_size].append(path)
                except OSError:
                    continue

        candidates = [group for group in self.size_map.values() if len(group) > 1]
        total_files = sum(len(group) for group in candidates)

        if total_files == 0:
            print("✅ No duplicates found.")
            return

        # -------- Pass 2: Hash duplicates only --------
        processed = 0
        for group in candidates:
            for file_path in group:
                processed += 1
                self.update_progress(processed, total_files, file_path)

                file_hash = self.get_file_hash(file_path)
                if file_hash:
                    self.hash_map[file_hash].append(file_path)
                    self.total_scanned += 1
                    logging.info(f"Hashed: {file_path}")

        print("\n")

        # -------- Handle duplicates --------
        for files in self.hash_map.values():
            if len(files) > 1:
                original = files[0]
                for dup in files[1:]:
                    try:
                        size = dup.stat().st_size
                        self.wasted_space_bytes += size
                        size_str = self.format_size(size)

                        if self.delete:
                            dup.unlink()
                            print(f"🗑️  DELETED: {dup} ({size_str})")
                        else:
                            print(f"📄 DUPLICATE: {dup} ({size_str})")
                    except Exception as e:
                        logging.error(f"Action failed on {dup}: {e}")

        self.print_summary()

    # ---------- Summary ----------
    def print_summary(self):
        print(
            f"\n{'=' * 40}\n"
            f"SUMMARY REPORT\n"
            f"{'=' * 40}\n"
            f"Files Hashed:   {self.total_scanned}\n"
            f"Wasted Space:  {self.format_size(self.wasted_space_bytes)}\n"
            f"Mode:          {'DELETE' if self.delete else 'DRY RUN'}\n"
            f"Log File:      {LOG_FILE}\n"
        )

# ---------------- Entry Point ----------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fast Duplicate File Finder")
    parser.add_argument("path", help="Directory to scan")
    parser.add_argument("--delete", action="store_true", help="Delete duplicates")
    args = parser.parse_args()

    DuplicateManager(args.path, args.delete).run()