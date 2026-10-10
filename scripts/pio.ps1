# Run PlatformIO inside firmware\xiao_esp32s3 (works whether or not pio is on PATH).
# Usage (from repo root):  .\scripts\pio.ps1 run                  # build
#                          .\scripts\pio.ps1 run -t upload        # build + flash (port auto-detected)
#                          .\scripts\pio.ps1 device monitor       # serial console, type 'help'
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\evk_common.ps1"
$pio = Get-Pio
$proj = Join-Path $PSScriptRoot '..\firmware\xiao_esp32s3'
Push-Location $proj
try { & $pio @args; exit $LASTEXITCODE } finally { Pop-Location }
