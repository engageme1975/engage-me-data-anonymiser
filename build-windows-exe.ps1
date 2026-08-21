param(
    [string]$Python = "python",
    [string]$OutputName = "Engage-Me-Data-Anonymiser"
)

$ErrorActionPreference = "Stop"

# desktop_app.py's APP_VERSION constant is the single source of truth for
# the app version, shown in the title bar and embedded into the exe's
# Windows file properties below - so a machine that already has an older
# build can be told apart from a new one without needing to compare file
# timestamps.
$versionMatch = Select-String -Path "desktop_app.py" -Pattern 'APP_VERSION\s*=\s*"([^"]+)"'
if (-not $versionMatch) {
    throw "Could not find APP_VERSION in desktop_app.py"
}
$appVersion = $versionMatch.Matches[0].Groups[1].Value
Write-Host "Building version $appVersion"

# Remove any previous build output first. PyInstaller's --clean flag only
# clears its own internal cache, not dist/<name> - without this, files that
# existed in an older build but were removed from a newer one (e.g. after
# dropping a dependency) can linger in dist/<name> and ship alongside the
# new build's files.
if (Test-Path "dist\$OutputName") { Remove-Item -Recurse -Force "dist\$OutputName" }
if (Test-Path "build\$OutputName") { Remove-Item -Recurse -Force "build\$OutputName" }

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

# Embed the version into the exe's Windows file properties (right-click ->
# Properties -> Details) so it can be confirmed on a machine without
# opening the app - useful when checking whether an install actually
# updated.
$versionParts = ($appVersion -split '\.') + @("0", "0", "0", "0") | Select-Object -First 4
$versionTuple = $versionParts -join ','
$versionFilePath = "version_info.txt"
@"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($versionTuple),
    prodvers=($versionTuple),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0,0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'Engage Me'),
        StringStruct(u'FileDescription', u'Engage-Me Data Anonymiser'),
        StringStruct(u'FileVersion', u'$appVersion'),
        StringStruct(u'InternalName', u'$OutputName'),
        StringStruct(u'OriginalFilename', u'$OutputName.exe'),
        StringStruct(u'ProductName', u'Engage-Me Data Anonymiser'),
        StringStruct(u'ProductVersion', u'$appVersion')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"@ | Out-File -FilePath $versionFilePath -Encoding utf8

Write-Host "Building Windows executable..."
# pyarrow and PIL are transitively installed for the Streamlit web app
# (requirements.txt) but desktop_app.py (Tkinter) never imports them - they
# were previously being swept into the bundle anyway (~90MB) by the
# --collect-all hooks below. Test suites bundled by --collect-all are
# likewise dead weight in a shipped build. Excluding all of them is a
# behaviour-neutral size cut, not a functional change.
& $Python -m PyInstaller --noconfirm --clean --onedir --name $OutputName `
    --version-file $versionFilePath `
    --collect-all en_core_web_md `
    --collect-all spacy `
    --collect-all thinc `
    --collect-all presidio_analyzer `
    --collect-all presidio_anonymizer `
    --exclude-module pyarrow `
    --exclude-module PIL `
    --exclude-module streamlit `
    --exclude-module spacy.tests `
    --exclude-module thinc.tests `
    --exclude-module pandas.tests `
    desktop_app.py

Remove-Item -Force $versionFilePath -ErrorAction SilentlyContinue

Write-Host "Build complete ($appVersion). Find the executable in dist\$OutputName\$OutputName.exe"
