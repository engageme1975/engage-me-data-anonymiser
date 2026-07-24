# Engage-Me Data Anonymiser

Self-hosted PII anonymisation for housing comments using Microsoft Presidio. All processing runs locally in your environment.

## Prerequisites
- Docker Desktop installed if you want the container path
- Windows users who want a local app can use the desktop app build script

## Quick Start
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
docker pull ttl.sh/engage-me-data-anonymiser:24h
docker run -p 8501:8501 ttl.sh/engage-me-data-anonymiser:24h
```

5. Open your browser at http://localhost:8501
6. Upload your Excel or CSV file.
7. Select one or more columns to anonymise.
8. Choose which entity types to redact, using the UK-aligned defaults or your own mix.
9. Click **Start Anonymisation**.
10. Download the resulting workbook (`beyond_anonymised_results.xlsx`).

## Windows desktop app
If you do not want Docker on Windows, this repo now includes a desktop app that can be packaged into an `.exe`.

1. Install Python 3.11 on Windows.
2. Open PowerShell in this folder.
3. Run:

```powershell
./build-windows-exe.ps1
```

4. Find the executable in `dist/Engage-Me-Data-Anonymiser/Engage-Me-Data-Anonymiser.exe`.
5. Open the app, choose a file, select columns and entity types, then save the anonymised workbook.

### py2exe option
If you prefer py2exe, install it in the same Windows Python environment and run:

```powershell
python -m pip install py2exe
python setup-py2exe.py py2exe
```

The executable is created under `dist/`.

### Build it here via GitHub Actions
If you want the `.exe` built for you, push the repo to GitHub and run the workflow named `Build Windows EXE`.

It produces a downloadable ZIP artifact containing the Windows build.

## Output Sheets
- `Anonymised Data`: original rows + one anonymised output column per selected source column
- `Detection Report`: each detected entity with source column, output column, row index, score, and span
- `Residual Flags` (if present): possible leftover patterns to manually review

## Notes
- No data is sent externally.
- Run a QA loop on a representative 400 to 600 comment sample before production use.
- Tune regex patterns, context terms, and threshold to improve precision and recall.

## Governance Summary
- Customer runs the image locally in their own environment.
- Raw identifiable data does not leave customer control.
