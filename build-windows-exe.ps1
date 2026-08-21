param(
    [string]$Python = "python",
    [string]$OutputName = "Engage-Me-Data-Anonymiser"
)

$ErrorActionPreference = "Stop"

Write-Host "Installing build dependencies..."
& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt pyinstaller

# spaCy's compiled backend (thinc/numpy_ops) needs the Visual C++ runtime
# DLLs to load. A freshly provisioned Windows machine often doesn't have
# them, which fails as an opaque "DLL load failed: numpy_ops" error deep
# inside spaCy import rather than a clear message here. Detect that case
# up front and self-heal via winget before it derails the build.
& $Python -c "import spacy" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "spaCy failed to import - this usually means the Visual C++ Redistributable is missing. Attempting to install it..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        winget install --id Microsoft.VCRedist.2015+.x64 -e --source winget --accept-package-agreements --accept-source-agreements
    } else {
        throw "winget is not available to auto-install the Visual C++ Redistributable. Install it manually from https://aka.ms/vs/17/release/vc_redist.x64.exe and re-run this script."
    }

    & $Python -c "import spacy" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "spaCy still fails to import after installing the Visual C++ Redistributable. Re-open this shell (PATH may need a refresh) and re-run the script; if it still fails, install https://aka.ms/vs/17/release/vc_redist.x64.exe manually."
    }
    Write-Host "Visual C++ Redistributable installed - spaCy now imports correctly."
}

& $Python -m spacy download en_core_web_md

Write-Host "Building Windows executable..."
& $Python -m PyInstaller --noconfirm --clean --onedir --name $OutputName `
    --collect-all en_core_web_md `
    --collect-all spacy `
    --collect-all thinc `
    --collect-all presidio_analyzer `
    --collect-all presidio_anonymizer `
    desktop_app.py

Write-Host "Build complete. Find the executable in dist\$OutputName\$OutputName.exe"
