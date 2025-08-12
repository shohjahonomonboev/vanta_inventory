$repo    = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$pidFile = Join-Path $repo ".vanta_prod.pid"
if (-not (Test-Path $pidFile)) { Write-Host "No PID file." -ForegroundColor Yellow; return }
$FlaskPid = (Get-Content $pidFile | Select-Object -First 1) -as [int]
Remove-Item $pidFile -ErrorAction SilentlyContinue
if (-not $FlaskPid) { Write-Host "Bad PID in file." -ForegroundColor Yellow; return }
$proc = Get-Process -Id $FlaskPid -ErrorAction SilentlyContinue
if ($proc -and ($proc.ProcessName -match "python|py")) {
  Stop-Process -Id $FlaskPid -Force
  Write-Host "Stopped Flask PID $FlaskPid." -ForegroundColor Green
} else {
  Write-Host "PID $FlaskPid not running (or not python)." -ForegroundColor Yellow
}
