# Run PlatformIO from the user's local install (pio is not on PATH).
# Usage (from repo root):  .\scripts\pio.ps1 run
#                          .\scripts\pio.ps1 run -t upload --upload-port COM8
#                          .\scripts\pio.ps1 device monitor -p COM8
$ErrorActionPreference = 'Stop'
$pio = Join-Path $env:USERPROFILE '.platformio\penv\Scripts\pio.exe'
if (-not (Test-Path $pio)) { throw "PlatformIO not found at $pio" }
$proj = Join-Path $PSScriptRoot '..\firmware\xiao_esp32s3'
Push-Location $proj
try { & $pio @args; exit $LASTEXITCODE } finally { Pop-Location }
