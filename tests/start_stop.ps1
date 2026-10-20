$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent

function Assert($condition, $message) {
  if (-not $condition) { throw $message }
}

# Keep the check in the background instead of opening the browser twice.
function Start-Process {
  param($FilePath, $ArgumentList, $WorkingDirectory, $WindowStyle,
    $RedirectStandardOutput, $RedirectStandardError, [switch]$Wait, [switch]$PassThru)
  if ($FilePath -eq 'http://localhost:3000') { return }
  Microsoft.PowerShell.Management\Start-Process @PSBoundParameters
}

function Invoke-Launcher($name) {
  $Root = $project
  $code = (Get-Content -LiteralPath "$project\$name.bat" -Raw) -split '(?m)^# POWERSHELL\r?$', 2
  & ([scriptblock]::Create($code[1]))
}
Assert (-not (Get-NetTCPConnection -State Listen -LocalPort 3000,8000 -ErrorAction SilentlyContinue)) 'Stop existing app services before running this check'

$foreign = $null
try {
  $foreign = Start-Process -FilePath (Get-Command node.exe).Source -ArgumentList @('-e', '"require(''http'').createServer((q,s)=>s.end(''test'')).listen(3000,''127.0.0.1'')"') -WindowStyle Hidden -PassThru
  for ($i = 0; $i -lt 20; $i++) {
    if (Get-NetTCPConnection -State Listen -LocalPort 3000 -ErrorAction SilentlyContinue) { break }
    Start-Sleep -Milliseconds 200
  }
  Assert (-not $foreign.HasExited) 'Test server did not start'
  $rejected = $false
  try { Invoke-Launcher 'start' } catch { $rejected = $_.Exception.Message -like '*used by another application*' }
  Assert $rejected 'Start must reject an unrelated app occupying the port'
  Invoke-Launcher 'stop'
  Assert ([bool](Get-Process -Id $foreign.Id -ErrorAction SilentlyContinue)) 'Stop killed an unrelated app'
} finally {
  if ($foreign) {
    Stop-Process -Id $foreign.Id -Force -ErrorAction SilentlyContinue
    $null = $foreign.WaitForExit(5000)
  }
}

try {
  Invoke-Launcher 'start'
  $first = @(Get-NetTCPConnection -State Listen -LocalPort 3000,8000).OwningProcess | Sort-Object -Unique
  Assert ($first.Count -eq 2) 'Both services must listen'
  Invoke-Launcher 'start'
  $second = @(Get-NetTCPConnection -State Listen -LocalPort 3000,8000).OwningProcess | Sort-Object -Unique
  Assert (-not (Compare-Object $first $second)) 'Repeated start created replacement processes'
} finally {
  Invoke-Launcher 'stop'
}
Invoke-Launcher 'stop'
Assert (-not (Get-NetTCPConnection -State Listen -LocalPort 3000,8000,8060 -ErrorAction SilentlyContinue)) 'App ports still listening after stop'
Assert ([bool](Get-NetTCPConnection -State Listen -LocalPort 5432 -ErrorAction SilentlyContinue)) 'Stop must preserve PostgreSQL'
Write-Host 'PASS: start, repeated start, stop, repeated stop, port conflict and unrelated-process isolation.'
