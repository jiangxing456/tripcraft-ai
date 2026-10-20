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
$PgBin = "D:\cloding\pgsql-portable\pgsql\bin"
$PgData = "D:\cloding\pgdata-tripcraft3"

$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 3000,8000 -ErrorAction SilentlyContinue)
foreach ($listener in $listeners) {
  $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
  if (-not $owner.CommandLine -or $owner.CommandLine.IndexOf("$Root\", [StringComparison]::OrdinalIgnoreCase) -lt 0) {
    throw "Port $($listener.LocalPort) is used by another application; nothing was stopped."
  }
}

function Test-PostgresReady {
  $check = Start-Process -FilePath "$PgBin\pg_isready.exe" `
    -ArgumentList @('-h', '127.0.0.1', '-p', '5432', '-q') `
    -Wait -PassThru -WindowStyle Hidden
  return ($check.ExitCode -eq 0)
}

Write-Host "1/3 PostgreSQL..."
if (-not (Test-PostgresReady)) {
  & "$PgBin\pg_ctl.exe" -D $PgData -l "D:\cloding\pgdata-tripcraft3.log" -o "-p 5432" -w -t 10 start
  if ($LASTEXITCODE -ne 0) {
    throw "PostgreSQL failed to start"
  }
}

Write-Host "2/3 Backend..."
if (8000 -notin $listeners.LocalPort) {
  Start-Process -FilePath "$Root\backend\.venv\Scripts\python.exe" `
    -ArgumentList @('main.py') `
    -WorkingDirectory "$Root\backend" `
    -WindowStyle Hidden `
    -RedirectStandardOutput "$Root\backend.stdout.log" `
    -RedirectStandardError "$Root\backend.stderr.log"
}

Write-Host "3/3 Frontend..."
if (3000 -notin $listeners.LocalPort) {
  $next = "`"$Root\client\node_modules\next\dist\bin\next`""
  Start-Process -FilePath (Get-Command node.exe).Source `
    -ArgumentList @($next, 'dev', '--port', '3000', '--turbopack') `
    -WorkingDirectory "$Root\client" `
    -WindowStyle Hidden `
    -RedirectStandardOutput "$Root\frontend.stdout.log" `
    -RedirectStandardError "$Root\frontend.stderr.log"
}

foreach ($url in @('http://127.0.0.1:8000/api/health', 'http://127.0.0.1:3000')) {
  $ready = $false
  for ($i = 0; $i -lt 40; $i++) {
    try {
      $null = Invoke-WebRequest -UseBasicParsing $url -TimeoutSec 2
      $ready = $true
      break
    } catch {
      Start-Sleep -Seconds 1
    }
  }
  if (-not $ready) {
    throw "Service unavailable: $url. Check *.stderr.log; run stop.bat to stop services."
  }
}

Write-Host "Ready: http://localhost:3000  |  Stop: stop.bat" -ForegroundColor Green
Start-Process 'http://localhost:3000'
