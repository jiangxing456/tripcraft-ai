@echo off
setlocal
set "TRIPCRAFT_ROOT=%~dp0"
set "TRIPCRAFT_SCRIPT=%~f0"
powershell -NoProfile -Command ^
  "$Root=$env:TRIPCRAFT_ROOT.TrimEnd([char]92);" ^
  "$code=(Get-Content -LiteralPath $env:TRIPCRAFT_SCRIPT -Raw) -split '(?m)^# POWERSHELL\r?$',2;" ^
  "& ([scriptblock]::Create($code[1]))"
if errorlevel 1 (pause & exit /b 1)
exit /b 0
# POWERSHELL
$ErrorActionPreference = "Stop"
# Match the project path, never kill unrelated apps just because they use the same port.
$processes = @(Get-CimInstance Win32_Process | Where-Object {
  $_.Name -in @('python.exe', 'node.exe') -and $_.CommandLine -and
  $_.CommandLine.IndexOf("$Root\", [StringComparison]::OrdinalIgnoreCase) -ge 0
})
foreach ($process in $processes) {
  Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
}
Write-Host "TripCraft stopped. PostgreSQL and Redis remain running." -ForegroundColor Green
