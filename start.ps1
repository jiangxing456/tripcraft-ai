$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$PgBin = "D:\cloding\pgsql-portable\pgsql\bin"
$PgData = "D:\cloding\pgdata-tripcraft3"
$PgLog = "D:\cloding\pgdata-tripcraft3.log"
$DbUrl = "postgresql://postgres:postgres@127.0.0.1:5432/tripcraft_ai"

function Test-Port([int]$Port, [int]$TimeoutMs = 1000) {
  $client = New-Object System.Net.Sockets.TcpClient
  try {
    $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
    if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
      return $false
    }
    $client.EndConnect($async)
    return $client.Connected
  } catch {
    return $false
  } finally {
    $client.Close()
  }
}

function Test-PostgresReady {
  $proc = Start-Process -FilePath "$PgBin\pg_isready.exe" -ArgumentList @("-h", "127.0.0.1", "-p", "5432", "-q") -Wait -PassThru -NoNewWindow
  return ($proc.ExitCode -eq 0)
}

Write-Host "1/3 Starting PostgreSQL..." -ForegroundColor Cyan
if (-not (Test-PostgresReady)) {
  & "$PgBin\pg_ctl.exe" -D $PgData -l $PgLog -o "-p 5432" -w -t 10 start | Out-Null
  Start-Sleep -Seconds 1
}
if (-not (Test-PostgresReady)) { throw "PostgreSQL failed to start on 5432" }
Write-Host "PostgreSQL OK" -ForegroundColor Green

Write-Host "2/3 Starting backend..." -ForegroundColor Cyan
if (-not (Test-Port 8000)) {
  Start-Process powershell -WorkingDirectory "$Root\backend" -ArgumentList @(
    "-NoExit",
    "-Command",
    "`$env:DATABASE_URL='$DbUrl'; .\.venv\Scripts\python.exe main.py"
  ) | Out-Null
}

$backendReady = $false
for ($i = 0; $i -lt 20; $i++) {
  try {
    $null = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8000/api/health" -TimeoutSec 2
    $backendReady = $true
    break
  } catch {
    Start-Sleep -Seconds 1
  }
}
if (-not $backendReady) { throw "Backend health check failed" }
Write-Host "Backend OK  http://127.0.0.1:8000" -ForegroundColor Green

Write-Host "3/3 Starting frontend..." -ForegroundColor Cyan
if (-not (Test-Port 3000)) {
  Start-Process powershell -WorkingDirectory "$Root\client" -ArgumentList @(
    "-NoExit",
    "-Command",
    "npx next dev --port 3000 --turbopack"
  ) | Out-Null
}

$frontendReady = $false
for ($i = 0; $i -lt 40; $i++) {
  try {
    $null = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:3000" -TimeoutSec 2
    $frontendReady = $true
    break
  } catch {
    Start-Sleep -Seconds 1
  }
}
if (-not $frontendReady) { throw "Frontend failed to start on 3000" }

Write-Host ""
Write-Host "All services are up." -ForegroundColor Green
Write-Host "Open: http://localhost:3000"
Start-Process "http://localhost:3000"
