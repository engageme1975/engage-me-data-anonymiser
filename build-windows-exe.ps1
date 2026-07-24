param(
    [string]$Python = "py -3",
    [string]$OutputName = "Engage-Me-Data-Anonymiser"
)

$ErrorActionPreference = "Stop"

Write-Host "Installing build dependencies..."
& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt pyinstaller
& $Python -m spacy download en_core_web_md

Write-Host "Building Windows executable..."
& $Python -m PyInstaller --noconfirm --clean --onedir --name $OutputName desktop_app.py

Write-Host "Build complete. Find the executable in dist\$OutputName\$OutputName.exe"
