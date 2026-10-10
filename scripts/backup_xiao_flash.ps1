# Dump the whole 8 MB flash of the XIAO ESP32S3 (read-only) so the factory
# firmware can be restored later. Run this BEFORE the first upload.
#
#   .\scripts\backup_xiao_flash.ps1 -Port COM8
#
# Restore:
#   & "$env:USERPROFILE\.platformio\penv\Scripts\python.exe" `
#     "$env:USERPROFILE\.platformio\packages\tool-esptoolpy\esptool.py" `
#     --chip esp32s3 --port COM8 write_flash 0 captures\xiao_flash_backup_<stamp>.bin
param(
  [string]$Port = 'COM8'
)
$ErrorActionPreference = 'Stop'
$py = Join-Path $env:USERPROFILE '.platformio\penv\Scripts\python.exe'
$esptool = Join-Path $env:USERPROFILE '.platformio\packages\tool-esptoolpy\esptool.py'
foreach ($p in $py, $esptool) { if (-not (Test-Path $p)) { throw "missing: $p" } }

$outDir = Join-Path $PSScriptRoot '..\captures'
New-Item -ItemType Directory -Force $outDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$out = Join-Path $outDir "xiao_flash_backup_$stamp.bin"

& $py $esptool --chip esp32s3 --port $Port flash_id
if ($LASTEXITCODE -ne 0) { throw "esptool flash_id failed" }
& $py $esptool --chip esp32s3 --port $Port read_flash 0 0x800000 $out
if ($LASTEXITCODE -ne 0) { throw "esptool read_flash failed" }

$hash = (Get-FileHash $out -Algorithm SHA256).Hash.ToLower()
Write-Host "backup: $out"
Write-Host "sha256: $hash"
