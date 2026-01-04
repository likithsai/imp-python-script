import argparse
import sys
import os
from pathlib import Path

# Fix: Add the 'src' directory to the Python path so imports work
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

try:
    # Matching your exact filenames from the screenshot
    from check_duplicate import DuplicateManager
    from optimise_video import VideoConverter
except ImportError as e:
    print(f"❌ Error: Could not find script files in {script_dir}.")
    print(f"Details: {e}")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Multi-Tool: Duplicate Finder & Video Optimizer")
    subparsers = parser.add_subparsers(dest="command", help="Choose a tool")

    # Duplicate Finder Command
    dup_parser = subparsers.add_parser("find-dupes", help="Find duplicate files")
    dup_parser.add_argument("path", help="Directory to scan")
    dup_parser.add_argument("--delete", action="store_true", help="Delete duplicates")

    # Video Optimizer Command
    vid_parser = subparsers.add_parser("optimize-video", help="Compress videos using FFmpeg")
    vid_parser.add_argument("path", help="Directory containing videos")

    args = parser.parse_args()

    # --- Structural Pattern Matching (Switch-Case) ---
    match args.command:
        case "find-dupes":
            print(f"🚀 Running Duplicate Finder on: {args.path}")
            DuplicateManager(args.path, args.delete).run()

        case "optimize-video":
            print(f"🚀 Running Video Optimizer on: {args.path}")
            VideoConverter(Path(args.path)).process_folder()
        
        case None:
            parser.print_help()
            
        case _:
            print(f"❓ Unknown command: {args.command}")
            parser.print_help()

if __name__ == "__main__":
    main()