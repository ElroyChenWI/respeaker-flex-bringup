# Shared helpers for scripts\*.ps1 (dot-source: . "$PSScriptRoot\evk_common.ps1")

# PlatformIO: prefer the user's install (~\.platformio\penv), else pio on PATH.
function Get-Pio {
  $local = Join-Path $env:USERPROFILE '.platformio\penv\Scripts\pio.exe'
  if (Test-Path $local) { return $local }
  $cmd = Get-Command pio -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  throw 'PlatformIO not found. Install it: https://platformio.org/install (VS Code extension or "pip install platformio")'
}

# esptool: returns the command prefix as an array, e.g. @('python.exe','esptool.py')
function Get-Esptool {
  $py = Join-Path $env:USERPROFILE '.platformio\penv\Scripts\python.exe'
  $tool = Join-Path $env:USERPROFILE '.platformio\packages\tool-esptoolpy\esptool.py'
  if ((Test-Path $py) -and (Test-Path $tool)) { return ,@($py, $tool) }
  $cmd = Get-Command esptool -ErrorAction SilentlyContinue
  if ($cmd) { return ,@($cmd.Source) }
  throw 'esptool not found. Build the firmware once with scripts\pio.ps1 (installs it) or "pip install esptool"'
}

# COM port of the XIAO ESP32S3 USB-Serial/JTAG (VID 303A, PID 1001).
function Find-EvkPort {
  if ($env:EVK_PORT) { return $env:EVK_PORT }
  $dev = Get-CimInstance Win32_PnPEntity |
    Where-Object { $_.PNPDeviceID -match 'VID_303A&PID_1001' -and $_.Name -match '\((COM\d+)\)' } |
    Select-Object -First 1
  if (-not $dev) { throw 'XIAO ESP32S3 (USB 303A:1001) not found - plug in the XIAO USB-C or pass -Port' }
  [void]($dev.Name -match '\((COM\d+)\)')
  return $Matches[1]
}
