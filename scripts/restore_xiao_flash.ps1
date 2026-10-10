# Write a full-flash backup (from backup_xiao_flash.ps1) back to the XIAO ESP32S3.
# This OVERWRITES the firmware currently on the XIAO.
#
#   .\scripts\restore_xiao_flash.ps1 captures\xiao_flash_backup_<stamp>.bin [-Port COM8]
param(
  [Parameter(Mandatory = $true)][string]$Image,
  [string]$Port = ''
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\evk_common.ps1"
if (-not (Test-Path $Image)) { throw "image not found: $Image" }
if ((Get-Item $Image).Length -ne 8MB) { throw "expected an 8 MB full-flash image: $Image" }
$esptool = Get-Esptool
if (-not $Port) { $Port = Find-EvkPort }
Write-Host "port: $Port  image: $Image"
& $esptool[0] $esptool[1..9] --chip esp32s3 --port $Port write_flash 0 $Image
exit $LASTEXITCODE
