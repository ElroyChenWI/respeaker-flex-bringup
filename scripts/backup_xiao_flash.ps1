# Dump the whole 8 MB flash of the XIAO ESP32S3 (read-only) so whatever firmware
# is on it now can be restored later. Run this BEFORE the first upload.
# Takes ~12 minutes over USB-Serial/JTAG.
#
#   .\scripts\backup_xiao_flash.ps1            # port auto-detected
#   .\scripts\backup_xiao_flash.ps1 -Port COM8
#
# Restore later with:  .\scripts\restore_xiao_flash.ps1 captures\xiao_flash_backup_<stamp>.bin
param(
  [string]$Port = ''
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\evk_common.ps1"
$esptool = Get-Esptool
if (-not $Port) { $Port = Find-EvkPort }

$outDir = Join-Path $PSScriptRoot '..\captures'
New-Item -ItemType Directory -Force $outDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$out = Join-Path $outDir "xiao_flash_backup_$stamp.bin"

Write-Host "port: $Port"
& $esptool[0] $esptool[1..9] --chip esp32s3 --port $Port flash_id
if ($LASTEXITCODE -ne 0) { throw "esptool flash_id failed" }
& $esptool[0] $esptool[1..9] --chip esp32s3 --port $Port read_flash 0 0x800000 $out
if ($LASTEXITCODE -ne 0) { throw "esptool read_flash failed" }

$hash = (Get-FileHash $out -Algorithm SHA256).Hash.ToLower()
Write-Host "backup: $out"
Write-Host "sha256: $hash"
