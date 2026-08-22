# Engage-Me Data Anonymiser

Self-hosted PII anonymisation for housing comments using Microsoft Presidio and spaCy. All processing runs locally in your environment.

## Prerequisites
- Docker Desktop if you want the container path
- Windows users who want a local app can use the desktop app build script or the GitHub Actions EXE build

## Quick Start (Docker / browser UI)
1. Make sure Docker Desktop is installed and running if you want the container path.
2. Open a terminal in this folder.
3. For a menu/app-style install on Linux, run:

```bash
./install-app.sh
```

4. Then open the app menu and launch Engage-Me Data Anonymiser, or run:

```bash
./run-anonymiser.sh
```

If you prefer to run the container directly:

```bash
docker pull ghcr.io/engageme1975/engage-me-data-anonymiser:latest
docker run -p 8501:8501 ghcr.io/engageme1975/engage-me-data-anonymiser:latest
```

5. Open your browser at http://localhost:8501
6. Upload your Excel or CSV file.
7. Select one or more columns to anonymise.
8. Choose which entity types to redact, using the UK-aligned defaults or your own mix.
9. Click **Start Anonymisation**.
10. Download the resulting workbook.

## Windows desktop app
If you do not want Docker on Windows, this repo includes a desktop app that can be packaged into an `.exe`.

1. Install Python 3.11 on Windows.
2. Open PowerShell in this folder.
3. Run:

```powershell
./build-windows-exe.ps1
```

4. Find the executable in `dist/Engage-Me-Data-Anonymiser/Engage-Me-Data-Anonymiser.exe`.
5. Open the app, choose a file, select columns and entity types, then save the anonymised workbook.

### Build via GitHub Actions
Push the repo to GitHub and run the workflow **Build Windows EXE**.

It produces a downloadable ZIP artifact containing the Windows build. **Rebuild and redistribute the EXE after performance / residual-name changes so testers (e.g. Dylan) are not still running an older freeze-prone binary.**

## Performance (large datasets)
The desktop app and core pipeline are designed for multi-thousand-row files:

- Processing runs on a **background thread** so the UI stays responsive.
- Progress is throttled and shows an estimated remaining time.
- You can **Cancel** a run at any time.
- Text is analysed in **batches** via Presidio `BatchAnalyzerEngine`, with worker count and batch size derived from the machine's CPU count.
- Files over ~3,000 rows show a large-file status note when loaded.

If you previously saw freezes around 10k–11k rows, rebuild the Windows EXE from current `main` and re-test. Older EXEs do not include the batching / background-thread changes.

### Hardware guidance
Benchmarked directly with enforced OS-level resource limits (Windows Job Objects - the same mechanism Docker uses), not estimated:

| Test | Result |
|---|---|
| 100,000-row / 2-column file, full run | 932.7s (~15.5 min) total (analysis + Excel write), 649MB peak memory |
| Same 100,000-row file, hard-capped at 1GB RAM | Succeeded with no slowdown (649MB peak, comfortably under the cap) |
| 8,000-row file, hard-capped at 512MB RAM | Succeeded with no slowdown |
| 8,000-row file, restricted to 1 CPU core | No difference vs 2 cores - this workload is single-threaded on a 2-core machine |

Takeaways:
- **RAM is not a practical concern** on modern hardware (even 2-4GB) once running a build that includes the streaming Excel writer (v1.1.2+) - the earlier `pd.ExcelWriter`/openpyxl default path could `MemoryError` on the Detection Report sheet for large files (one row per detected entity, not per input row) since it built the whole workbook in memory before saving.
- **CPU core count matters less than expected below 3 cores** - worker count (`_worker_process_count()` in `anonymization_core.py`) is `cpu_count - 1`, so a 2-core machine only ever gets 1 worker regardless. Machines with 3+ cores get real multi-process parallelism, but this hasn't been benchmarked (no machine with more cores was available for testing).
- **CPU speed, not core count or RAM, is the most likely bottleneck on genuinely low-spec hardware** - this can't be simulated with OS resource limits, only tested on the actual hardware.
- Expect roughly 200-230 cells/sec (rows x selected columns) as a baseline; scale linearly for your file size.

## Residual name coverage
In addition to standard Presidio + spaCy NER, the tool includes:

- `Name: ...` field label recogniser (website form headers)
- Title + name patterns (`Mr` / `Mrs` / `Miss` / `Ms` + name)
- `scan_missed_proper_nouns` (in `beyond_recognizers.py`): flags spaCy proper-noun (POS=PROPN) tokens that fall outside every redacted span, reading the model's actual part-of-speech tags and raw entity labels rather than guessing sentence phrasing. It also surfaces the model's off-label tag when one exists (e.g. a missed name spaCy classified as `ORGANIZATION` or `DATE_TIME` instead of `PERSON`) - information Presidio's own `analyze()` output discards. An earlier verb-phrase regex list was removed after independent (Faker-generated) test data showed it added zero coverage beyond its own exact wording.

Review the **Residual Flags** sheet after each run. Residual items are candidates for manual review, not automatic redactions of every capitalised word. No detection approach reaches 100% recall on free text - industry benchmarks put general-purpose PII tools at 57-73% recall on real enterprise data, so the review step is load-bearing, not a formality.

### Updating to a new version
Releases are published on the [Releases page](https://github.com/engageme1975/engage-me-data-anonymiser/releases) as `Engage-Me-Data-Anonymiser-windows.zip`, tagged with a version (e.g. `v1.1.0`). The app's title bar shows its version, so you can confirm which build is running without checking file dates.

To update a machine that already has the app installed:
1. Close the app if it is running (Windows can't overwrite a file that's in use).
2. Delete the old `Engage-Me-Data-Anonymiser` folder entirely, rather than extracting the new zip on top of it - this avoids old files that no longer exist in the new build being left behind.
3. Extract the new release zip in its place.

## Output Sheets
- `Anonymised Data`: original rows + one anonymised output column per selected source column
- `Detection Report`: each detected entity with source column, output column, row index, score, and span
- `Residual Flags` (if present): possible leftover patterns to manually review (including possible person names)

## Notes
- No data is sent externally.
- Run a QA loop on a representative 400 to 600 comment sample before production use.
- Tune regex patterns, context terms, and the detection threshold slider to balance precision and recall.
- Recommended interactive range is comfortable for several thousand rows; very large files still benefit from a rebuilt EXE with the current batching path.

## Governance Summary
- Customer runs the image or desktop app locally in their own environment.
- Raw identifiable data does not leave customer control.
