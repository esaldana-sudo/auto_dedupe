
#!/usr/bin/env python3
"""
auto_dedupe_v8.py

Sort and deduplicate media by content hash and date.
- Uniques: moved to <output-dir>/YYYY/MM/
- Duplicates (default): moved to <output-dir>/_duplicates/YYYY/MM/
- Duplicates with --delete: deleted (no archive)
- State: stored under ./res (hash DB, checkpoint), logs under ./log
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from datetime import datetime

try:
    from PIL import Image, ExifTags
except Exception:
    Image = None
    ExifTags = None

try:
    from tqdm import tqdm
except Exception:
    # Fallback no-op tqdm
    def tqdm(iterable, **kwargs):
        return iterable

# Anchors for state next to this script
BASE = Path(__file__).resolve().parent
RES_DIR = BASE / "res"
LOG_DIR = BASE / "log"
RES_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
HASH_DB_FILE = RES_DIR / "familia_hashes.json"
CHECKPOINT_FILE = RES_DIR / ".checkpoint.json"

# These are set from --output-dir at runtime
STATIC_OUTPUT_ROOT = None
DUP_ARCHIVE_ROOT = None
NO_DATE_ROOT = None

# File type support
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".bmp", ".gif", ".cr2", ".nef", ".arw", ".dng"}
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".mts", ".3gp", ".wmv"}
EXCLUDE_PARTS = {"_duplicates", "_duplicates_bad"}

def _safe_load_json(path: Path, default):
    try:
        if path.exists() and path.stat().st_size > 0:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default

def _safe_write_json(path: Path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)

def is_supported(path: Path) -> bool:
    ext = path.suffix.lower()
    return ext in SUPPORTED_IMAGE_EXTENSIONS or ext in SUPPORTED_VIDEO_EXTENSIONS

def is_excluded(path: Path) -> bool:
    return any(part.lower() in EXCLUDE_PARTS for part in path.parts)

def get_exif_datetime(p: Path):
    if Image is None:
        return None
    try:
        with Image.open(p) as img:
            exif = getattr(img, "_getexif", lambda: None)()
            if not exif:
                return None
            # Map EXIF tags
            tag_map = {}
            if ExifTags is not None and hasattr(ExifTags, "TAGS"):
                tag_map = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
            for key in ("DateTimeOriginal", "CreateDate", "DateTime"):
                v = tag_map.get(key)
                if isinstance(v, bytes):
                    v = v.decode(errors="ignore")
                if isinstance(v, str):
                    # Common EXIF format "YYYY:MM:DD HH:MM:SS"
                    v = v.replace(":", "-", 2)
                    try:
                        return datetime.fromisoformat(v)
                    except Exception:
                        # Fallback parse
                        try:
                            return datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
                        except Exception:
                            continue
    except Exception:
        return None
    return None

def get_file_date(p: Path) -> datetime:
    # Prefer EXIF for images
    if p.suffix.lower() in {".jpg", ".jpeg", ".tiff"}:
        dt = get_exif_datetime(p)
        if dt:
            return dt
    # Fallback to modified time
    try:
        ts = p.stat().st_mtime
        return datetime.fromtimestamp(ts)
    except Exception:
        return datetime.fromtimestamp(0)

def get_ym_folder(dt: datetime) -> str:
    if not isinstance(dt, datetime) or dt.timestamp() <= 0:
        return "_no_date"
    return f"{dt.year:04d}/{dt.month:02d}"

def ensure_dest_path(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        return dest
    i = 1
    while True:
        candidate = dest.with_name(f"{dest.stem}_{i}{dest.suffix}")
        if not candidate.exists():
            return candidate
        i += 1

def hash_file(p: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None

def archive_duplicate(file_path: Path, date_folder: str) -> Path:
    if date_folder == "_no_date":
        dest_base = NO_DATE_ROOT
    else:
        dest_base = DUP_ARCHIVE_ROOT / date_folder
    dest_path = ensure_dest_path(dest_base / file_path.name)
    shutil.move(str(file_path), str(dest_path))
    return dest_path

def move_unique(file_path: Path, date_folder: str) -> Path:
    # Move into YYYY/MM or _no_date under STATIC_OUTPUT_ROOT
    if date_folder == "_no_date":
        dest_base = NO_DATE_ROOT
    else:
        dest_base = STATIC_OUTPUT_ROOT / date_folder
    dest_path = ensure_dest_path(dest_base / file_path.name)
    shutil.move(str(file_path), str(dest_path))
    return dest_path

def iter_files(root: Path):
    for dirpath, _, filenames in os.walk(root):
        d = Path(dirpath)
        if is_excluded(d):
            continue
        for name in filenames:
            p = d / name
            if is_supported(p) and not is_excluded(p):
                yield p

def main():
    parser = argparse.ArgumentParser(description="Sort and deduplicate files by date and hash.")
    parser.add_argument("--input-dir", required=True, help="Source directory to scan")
    parser.add_argument("--output-dir", required=True, help="Root output directory (e.g., /mnt/my_drive/media)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without modifying files")
    parser.add_argument("--delete", action="store_true", help="Delete duplicates instead of archiving")
    parser.add_argument("--dedupe-only", action="store_true", help="Only deduplicate (no sorting for uniques)")
    parser.add_argument("--input-list", help="Path to .txt file containing file paths to scan")
    parser.add_argument("--limit", type=int, help="Limit number of files to process")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    parser.add_argument("--log-file", help="Path to write a detailed run log")
    args = parser.parse_args()

    # Configure output roots from --output-dir
    global STATIC_OUTPUT_ROOT, DUP_ARCHIVE_ROOT, NO_DATE_ROOT
    STATIC_OUTPUT_ROOT = Path(args.output_dir).resolve()
    DUP_ARCHIVE_ROOT = STATIC_OUTPUT_ROOT / "_duplicates"
    NO_DATE_ROOT = STATIC_OUTPUT_ROOT / "_no_date"

    # Guardrail: refuse input-dir == output-dir unless dedupe-only
    in_dir = Path(args.input_dir).resolve()
    if in_dir == STATIC_OUTPUT_ROOT and not args.dedupe_only:
        print("Refusing to run with --input-dir equal to --output-dir without --dedupe-only.", file=sys.stderr)
        sys.exit(2)

    # Load state
    hash_db = _safe_load_json(HASH_DB_FILE, {})
    checkpoint = _safe_load_json(CHECKPOINT_FILE, {})  # dict of processed paths
    if not isinstance(hash_db, dict):
        hash_db = {}
    if not isinstance(checkpoint, dict):
        checkpoint = {}

    # For logs
    log_lines = []
    def log(msg):
        if args.verbose:
            print(msg)
        log_lines.append(msg + "\n")

    # Prepare file list
    files = []
    if args.input_list:
        try:
            with open(args.input_list, "r", encoding="utf-8") as f:
                for line in f:
                    p = Path(line.strip())
                    if p.exists() and is_supported(p) and not is_excluded(p):
                        files.append(p)
        except Exception as e:
            print(f"Failed to read input list: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        files = list(iter_files(in_dir))

    if args.limit:
        files = files[: args.limit]

    total = 0
    uniques = 0
    duplicates = 0
    hash_failures = 0
    move_failures = 0
    delete_failures = 0

    for p in tqdm(files, desc="Processing"):
        total += 1
        full_path = p.resolve()
        rel_key = str(full_path)

        if checkpoint.get(rel_key):
            log(f"SKIP (checkpoint): {full_path}")
            continue

        file_hash = hash_file(full_path)
        if not file_hash:
            hash_failures += 1
            log(f"HASH_FAIL | {full_path}")
            checkpoint[rel_key] = True
            continue

        # Mark as seen to avoid reprocessing on reruns
        checkpoint[rel_key] = True

        if file_hash in hash_db:
            duplicates += 1
            date_folder = get_ym_folder(get_file_date(full_path))
            if not args.dry_run:
                if args.delete:
                    try:
                        full_path.unlink(missing_ok=True)
                    except Exception as e:
                        delete_failures += 1
                        log(f"DELETE_FAIL | {full_path} | {e}")
                else:
                    try:
                        archive_path = archive_duplicate(full_path, date_folder)
                        log(f"DUP_ARCHIVE | {full_path} -> {archive_path}")
                    except Exception as e:
                        move_failures += 1
                        log(f"ARCHIVE_FAIL | {full_path} | {e}")
            else:
                log(f"SIMULATE_DUP | {full_path}")
            continue

        # Unique
        hash_db[file_hash] = {
            "path": rel_key,
            "timestamp": datetime.now().isoformat(timespec="seconds")
        }

        if not args.dedupe_only:
            date_folder = get_ym_folder(get_file_date(full_path))
            if not args.dry_run:
                try:
                    dest_path = move_unique(full_path, date_folder)
                    uniques += 1
                    log(f"UNIQUE_MOVE | {full_path} -> {dest_path}")
                except Exception as e:
                    move_failures += 1
                    log(f"MOVE_FAIL | {full_path} | {e}")
            else:
                uniques += 1
                log(f"SIMULATE_UNIQUE | {full_path}")
        else:
            # Only record hash, do not move
            uniques += 1
            log(f"HASH_ONLY | {full_path}")

    # Write state unless dry run
    if not args.dry_run:
        _safe_write_json(HASH_DB_FILE, hash_db)
        _safe_write_json(CHECKPOINT_FILE, checkpoint)

    # Summary
    summary = (
        f"Total: {total} | Uniques: {uniques} | Duplicates: {duplicates} | "
        f"HashFails: {hash_failures} | MoveFails: {move_failures} | DeleteFails: {delete_failures}"
    )
    print(summary)
    log_lines.append(summary + "\n")

    # Persist log if requested
    if args.log_file:
        try:
            log_path = Path(args.log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("w", encoding="utf-8") as f:
                f.writelines(log_lines)
        except Exception as e:
            # Also write a basic error log into LOG_DIR
            err_path = LOG_DIR / f"errors_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
            with err_path.open("w", encoding="utf-8") as f:
                f.write(f"Failed to write log file: {e}\n")
                f.writelines(log_lines)

if __name__ == "__main__":
    main()
