# Clone Seeed's reSpeaker Flex repo (XMOS firmware images + python_control)
# into third_party/ at a pinned commit. third_party/ is git-ignored.
#
#   .\scripts\fetch_vendor.ps1
param(
  [string]$Commit = '99a5047129c158beb655daf5f38b325ebef0974a'  # main @ 2026-09-29
)
$ErrorActionPreference = 'Stop'
$dst = Join-Path $PSScriptRoot '..\third_party\reSpeaker_Flex'
if (-not (Test-Path $dst)) {
  git clone https://github.com/respeaker/reSpeaker_Flex $dst
  if ($LASTEXITCODE -ne 0) { throw 'git clone failed' }
}
git -C $dst fetch --quiet origin
git -C $dst checkout --quiet $Commit
if ($LASTEXITCODE -ne 0) { throw "checkout $Commit failed" }
Write-Host "reSpeaker_Flex @ $(git -C $dst rev-parse --short HEAD) -> $dst"
