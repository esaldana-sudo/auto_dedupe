# auto_dedupe

Sort and de-duplicate photos/videos by **content hash** and organize uniques into `YYYY/MM` folders. Duplicates are archived (or deleted with a flag). State (hash DB + checkpoint) and logs are kept next to the script so re-runs are fast and idempotent.

## Repo layout

```
auto_dedupe.py        # main tool (Python)
run_auto_dedupe.sh    # wrapper to run with env + logging + locking
config.env            # environment config (paths, venv), not tracked
requirements.txt      # Python deps (Pillow, tqdm)
```

---

## Quick start

1) **Create a venv and install deps**
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

2) **Copy and edit `config.env`**
```bash
cp config.env config.env.example   # (optional backup)
# edit config.env with your paths
```

`config.env` variables:
- `BASE_DIR` (repo root)
- `VENV_PY` (path to venv python)
- `SCRIPT` (path to auto_dedupe.py)
- `INPUT` (source folder to scan)
- `OUTPUT` (media folder for sorted files)
- `LOG_DIR`, `LOG_FILE`, `LOCKFILE` (logging/locking)

3) **Run via the wrapper**
```bash
bash ./run_auto_dedupe.sh
```

---

## Usage (Python CLI)

```bash
python auto_dedupe.py \
  --input-dir /path/to/incoming \
  --output-dir /path/to/media \
  [--dry-run] [--delete] [--dedupe-only] \
  [--input-list paths.txt] [--limit N] [--verbose] \
  [--log-file /path/to/logfile.log]
```

### Features
- **Hashing:** SHA-256 over file contents.
- **Dates:** EXIF > file mtime > `_no_date`.
- **Uniques:** moved to `<OUTPUT>/YYYY/MM/`.
- **Duplicates:** archived under `_duplicates/` or deleted with `--delete`.
- **State & logs:** `res/familia_hashes.json`, `res/.checkpoint.json`, logs in `log/`.

Guardrail: refuses `--input-dir == --output-dir` unless `--dedupe-only`.

---

## Automation

Cron example:
```cron
0 * * * * cd /opt/auto_dedupe && bash ./run_auto_dedupe.sh >> /opt/auto_dedupe/log/runner.log 2>&1
```

systemd example:
```ini
[Unit]
Description=Auto Dedupe Ingest
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/auto_dedupe
ExecStart=/bin/bash /opt/auto_dedupe/run_auto_dedupe.sh
User=eddie
Group=eddie
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

---

## File types

Images: `.jpg .jpeg .png .tiff .bmp .gif .cr2 .nef .arw .dng`  
Videos: `.mp4 .mov .avi .mkv .mts .3gp .wmv`

---

## Logs & state

- Per-run logs in `log/ingest_YYYYMMDD_HHMM.log`, with `log/latest.log` symlink.
- Hash DB + checkpoint in `res/`.
- Summary line at end:
  ```
  Total: X | Uniques: Y | Duplicates: Z | HashFails: A | MoveFails: B | DeleteFails: C
  ```

---

## Safety

- Run with `--dry-run` first.
- Keep backups.
- Ensure permissions allow moves.
- Delete checkpoint (`res/.checkpoint.json`) if you want to rescan.

---

## Development

```bash
. .venv/bin/activate
pip install -r requirements.txt
```

- `Pillow` for EXIF date extraction.
- `tqdm` for progress bars.

---





