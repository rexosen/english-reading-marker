param(
    [string]$DeliveryPath
)

$ErrorActionPreference = 'Stop'

$projectRoot = $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$source = Join-Path $projectRoot 'src\main.py'
$sample = Join-Path $projectRoot 'assets\Online_Classes_原文.txt'
$distributionRoot = if ([string]::IsNullOrWhiteSpace($DeliveryPath)) {
    Join-Path $projectRoot 'outputs\windows'
} else {
    [System.IO.Path]::GetFullPath($DeliveryPath)
}
$buildRoot = Join-Path $projectRoot 'build\pyinstaller'

if (!(Test-Path -LiteralPath $python)) {
    throw 'Create the project virtual environment and install requirements.txt first.'
}

New-Item -ItemType Directory -Path $distributionRoot -Force | Out-Null

& $python -m PyInstaller --noconfirm --onedir --windowed `
    --name EnglishReadingMarker `
    --add-data "$sample;assets" `
    --add-data "$(Join-Path $projectRoot 'assets\dictionary.sqlite3');assets" `
    --add-data "$(Join-Path $projectRoot 'assets\ECDICT-LICENSE.txt');assets" `
    --distpath $distributionRoot `
    --workpath $buildRoot `
    --specpath $projectRoot `
    $source

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$internal = Join-Path $distributionRoot 'EnglishReadingMarker\_internal'
foreach ($incompatibleIcuFile in @('icuuc.dll', 'icudt78.dll')) {
    $path = Join-Path $internal $incompatibleIcuFile
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path
    }
}

Write-Host "Build complete: $(Join-Path $distributionRoot 'EnglishReadingMarker\EnglishReadingMarker.exe')"
