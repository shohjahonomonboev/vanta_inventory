$ErrorActionPreference = "Stop"
$PORT = 5101
$repo = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$pythonExe = Join-Path $repo "venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
  $pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
  if (-not $pythonExe) { $pythonExe = "python" }
}
if (Test-NetConnection -ComputerName 127.0.0.1 -Port $PORT -InformationLevel Quiet) {
  Write-Host "Port $PORT already in use." -ForegroundColor Yellow
  return
}
$pidFile = Join-Path $repo ".vanta_prod.pid"
$proc = Start-Process -FilePath $pythonExe `
  -ArgumentList @("-m","flask","--app","app.py","run","--host","127.0.0.1","--port","$PORT","--no-reload") `
  -WorkingDirectory $repo -WindowStyle Hidden -PassThru
$proc.Id | Out-File -Encoding ascii $pidFile
Write-Host "Started Flask PID $($proc.Id) on http://127.0.0.1:$PORT" -ForegroundColor Green
