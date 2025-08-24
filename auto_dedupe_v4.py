
import os
import hashlib
import shutil
import json
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from PIL import Image
from PIL.ExifTags import TAGS
from tqdm import tqdm

# ------------------ CONFIG ------------------ #
SUPPORTED_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.tiff', '.bmp', '.gif',
    '.cr2', '.nef', '.arw', '.dng',
    '.mp4', '.mov', '.avi', '.mkv', '.mts', '.3gp', '.wmv'
}
HASH_DB_FILE = "res/familia_hashes.json"
CHECKPOINT_FILE = "res/.checkpoint.json"
DUPLICATE_FOLDER = "/mnt/my_drive/media/_duplicates"
NO_DATE_FOLDER = "/mnt/my_drive/media/_no_date"
# ------------------------------------------- #

def compute_sha256(file_path, block_size=65536):
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            for block in iter(lambda: f.read(block_size), b''):
                sha256.update(block)
        return sha256.hexdigest()
    except Exception:
        return None

def get_exif_date(file_path):
    try:
        img = Image.open(file_path)
        exif = img._getexif()
        if not exif:
            return None
        for tag_id, value in exif.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag in ["DateTimeOriginal", "CreateDate"]:
                return value.replace(":", "-").split(" ")[0]
    except:
        return None
    return None

def get_file_date(file_path):
    ext = file_path.suffix.lower()
    if ext in ['.jpg', '.jpeg', '.tiff']:
        exif_date = get_exif_date(file_path)
        if exif_date:
            return exif_date
    stat = file_path.stat()
    return datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d')

def get_ym_folder(date_str):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{dt.year:04d}/{dt.month:02d}"
    except:
        return NO_DATE_FOLDER

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def is_excluded(path):
    return any(part.lower() in ["_duplicates", "_duplicates_bad"] for part in path.parts)

def archive_duplicate(file_path, output_dir, date_folder):
    dest_base = Path(output_dir) / DUPLICATE_FOLDER / date_folder
    dest_base.mkdir(parents=True, exist_ok=True)
    dest_path = dest_base / file_path.name
    i = 1
    while dest_path.exists():
        dest_path = dest_base / f"{file_path.stem}_{i}{file_path.suffix}"
        i += 1
    shutil.copy2(file_path, dest_path)
    return str(dest_path)

def move_to_output(file_path, output_dir, date_folder):
    dest_base = Path(output_dir) / date_folder
    dest_base.mkdir(parents=True, exist_ok=True)
    dest_path = dest_base / file_path.name
    i = 1
    while dest_path.exists():
        dest_path = dest_base / f"{file_path.stem}_{i}{file_path.suffix}"
        i += 1
    shutil.copy2(file_path, dest_path)
    return str(dest_path)

def get_all_files(input_dir, input_list, limit):
    files = []

    if input_list:
        with open(input_list, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    path = Path(line)
                    if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                        files.append(path)
    else:
        for root, _, filenames in os.walk(input_dir):
            for file in filenames:
                full_path = Path(root) / file
                if full_path.suffix.lower() in SUPPORTED_EXTENSIONS and not is_excluded(full_path.relative_to(input_dir)):
                    files.append(full_path)

    return files[:limit] if limit else files

def main(input_dir, output_dir, dry_run=False, delete=False, dedupe_only=False, input_list=None, limit=None, verbose=False, log_file=None):
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    hash_db = load_json(HASH_DB_FILE)
    checkpoint = load_json(CHECKPOINT_FILE)
    seen = set()
    duplicates = 0
    hash_failures = 0
    copy_failures = 0
    error_log_lines = []
    moved = 0

    files = get_all_files(input_dir, input_list, limit)
    pbar = tqdm(files, desc="Processing", unit="file")

    log_lines = []

    def log(msg):
        nonlocal log_lines
        if verbose:
            print(msg)
        if log_file:
            log_lines.append(msg)

    for full_path in pbar:
        rel_path = str(full_path)
        if rel_path in checkpoint:
            continue

        file_hash = compute_sha256(full_path)
        if not file_hash:
            hash_failures += 1
            error_log_lines.append(f"HASH_FAIL | {full_path}")
            continue
        seen.add(file_hash)
        checkpoint[rel_path] = True

        if file_hash in hash_db:
            duplicates += 1
            date_folder = get_ym_folder(get_file_date(full_path))
            if not dry_run:
                archive_path = archive_duplicate(full_path, output_dir, date_folder)
                if delete:
                    try:
                        full_path.unlink(missing_ok=True)
                    except Exception as e:
                        copy_failures += 1
                        error_log_lines.append(f"DELETE_FAIL | {full_path} | {e}")
            log(f"🟡 Duplicate: {full_path}")
            continue

        if not dedupe_only:
            date_folder = get_ym_folder(get_file_date(full_path))
            if not dry_run:
                try:
                    output_path = move_to_output(full_path, output_dir, date_folder)
                except Exception as e:
                    copy_failures += 1
                    error_log_lines.append(f"MOVE_FAIL | {full_path} | {e}")
                    continue
                hash_db[file_hash] = {
                    "path": str(full_path),
                    "moved_to": output_path,
                    "timestamp": datetime.now().isoformat()
                }
            moved += 1
            log(f"✅ Sorted: {full_path}")

    if not dry_run:
        save_json(HASH_DB_FILE, hash_db)
        save_json(CHECKPOINT_FILE, checkpoint)

    summary = f"""
📊 Summary
   Total scanned : {len(files)}
   Duplicates    : {duplicates}
   Moved         : {moved}
   Skipped       : {len(files) - moved - duplicates}
"""
    print(summary)
    print(f"   Hash Failures : {hash_failures}")
    print(f"   Copy Errors   : {copy_failures}")
    if error_log_lines:
        err_path = "log" / f"errors_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
        Path(err_path).parent.mkdir(parents=True, exist_ok=True)
        with open(err_path, "w", encoding="utf-8") as ef:
            ef.write("\n".join(error_log_lines))
        print(f"❌ Errors written to: {err_path}")

    if log_file:
        log_lines.append(summary)
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("".join(log_lines))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sort and deduplicate files by date and hash.")
    parser.add_argument("--input-dir", required=True, help="Source directory to scan")
    parser.add_argument("--output-dir", required=True, help="Destination root directory")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without modifying files")
    parser.add_argument("--delete", action="store_true", help="Delete duplicates instead of archiving")
    parser.add_argument("--dedupe-only", action="store_true", help="Only deduplicate (no sorting)")
    parser.add_argument("--input-list", help="Path to .txt file containing file paths to scan")
    parser.add_argument("--limit", type=int, help="Limit number of files to process")
    parser.add_argument("--verbose", action="store_true", help="Enable detailed output")
    parser.add_argument("--log-file", help="Optional log file to write output")

    args = parser.parse_args()
    main(args.input_dir, args.output_dir, args.dry_run, args.delete, args.dedupe_only, args.input_list, args.limit, args.verbose, args.log_file)
