
# auto_dedupe

Sort and deduplicate media by content hash and date.

## Requirements
- Python 3.10+
- Pillow
- tqdm

## Install
Use a virtual environment and install dependencies:
```
python -m venv .venv
source .venv/bin/activate
pip install pillow tqdm
```

## One-time seeding
Seed the hash database from your existing organized library. This does not move files.
```
python auto_dedupe_v8.py   --input-dir /mnt/my_drive/media   --output-dir /mnt/my_drive/media   --dedupe-only --verbose   --log-file log/seed_media_$(date +%Y%m%d_%H%M).txt
```

## Daily use
Run on your staging folder to move uniques and archive duplicates.
```
python auto_dedupe_v8.py   --input-dir /mnt/my_drive/_Staging   --output-dir /mnt/my_drive/media   --verbose --log-file log/run_$(date +%Y%m%d_%H%M).txt
```

Delete duplicates instead of archiving:
```
python auto_dedupe_v8.py   --input-dir /mnt/my_drive/_Staging   --output-dir /mnt/my_drive/media   --delete --verbose
```

## Behavior
- Uniques are moved into `<output-dir>/YYYY/MM/`
- Duplicates are moved into `<output-dir>/_duplicates/YYYY/MM/`
- With `--delete`, duplicates are deleted
- State is stored in `./res` and `./log` next to the script
- Supported images: .jpg .jpeg .png .tiff .bmp .gif .cr2 .nef .arw .dng
- Supported videos: .mp4 .mov .avi .mkv .mts .3gp .wmv
- Paths containing `_duplicates` or `_duplicates_bad` are skipped

## Guardrails
The script refuses to run with `--input-dir` equal to `--output-dir` unless `--dedupe-only` is provided.

## Notes
- Checkpointing prevents reprocessing file paths on later runs
- If you lose the hash database, rerun the seeding pass on your library
