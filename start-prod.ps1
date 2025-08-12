# start-prod.ps1 — local prod-like server on :5100 (venv-aware)
param([switch]$Foreground)

# Resolve repo dir from script context (fallback to current dir)
$repo = if ($PSScriptRoot) { $PSScriptRoot } elseif ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path } else { (Get-Location).Path }

# Bail politely if port in use
if (Test-NetConnection -ComputerName 127.0.0.1 -Port 5100 -InformationLevel Quiet) {
  Write-Host "Port 5100 already in use — skipping start." -ForegroundColor Yellow
  return
}

# Helper to run Flask with the right Python
function Start-Flask5100 {
  param([string]$Interpreter)
  $env:ENV = "prod"
  $env:FLASK_APP = "app.py"
  $env:FLASK_ENV = "production"
  $env:PYTHONUNBUFFERED = "1"
  & $Interpreter -m flask run --host 127.0.0.1 --port 5100 --no-reload
}

# Choose interpreter: prefer repo venv, else py -3, else python
$venvPy = Join-Path $repo "venv\Scripts\python.exe"
$runner = if (Test-Path $venvPy) {
  $venvPy
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
  "py"  # we'll pass -3 in the call
} else {
  "python"
}

if ($Foreground) {
  Push-Location $repo
  if ($runner -eq "py") { py -3 -m flask run --host 127.0.0.1 --port 5100 --no-reload }
  else { Start-Flask5100 -Interpreter $runner }
  Pop-Location
} else {
  Start-Job -Name vanta_prod -ArgumentList $repo, $runner -ScriptBlock {
    param($r, $run)
    Set-Location $r
    if ($run -eq "py") {
      $env:ENV = "prod"; $env:FLASK_APP = "app.py"; $env:FLASK_ENV = "production"; $env:PYTHONUNBUFFERED = "1"
      py -3 -m flask run --host 127.0.0.1 --port 5100 --no-reload
    } else {
      $env:ENV = "prod"; $env:FLASK_APP = "app.py"; $env:FLASK_ENV = "production"; $env:PYTHONUNBUFFERED = "1"
      & $run -m flask run --host 127.0.0.1 --port 5100 --no-reload
    }
  } | Out-Null

  Write-Host "vanta_prod starting on http://127.0.0.1:5100 ..." -ForegroundColor Green
  Start-Sleep -Seconds 2
  if (Test-NetConnection -ComputerName 127.0.0.1 -Port 5100 -InformationLevel Quiet) {
    Write-Host "vanta_prod is up." -ForegroundColor Green
  } else {
    Write-Host "vanta_prod failed to bind :5100 (tail logs with: Receive-Job -Name vanta_prod -Keep | Select -Last 120)." -ForegroundColor Red
  }
}
