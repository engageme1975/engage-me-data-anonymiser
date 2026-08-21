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

## Residual name coverage
In addition to standard Presidio + spaCy NER, the tool includes:

- `Name: ...` field label recogniser (website form headers)
- Title + name patterns (`Mr` / `Mrs` / `Miss` / `Ms` + name)
- Residual scan flags for leftover titled names, untitled call-log names, postcodes, phones, NINOs, and long digit sequences

Review the **Residual Flags** sheet after each run. Residual items are candidates for manual review, not automatic redactions of every capitalised word.

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
