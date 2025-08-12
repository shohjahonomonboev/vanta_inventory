# restart-prod.ps1 — restart local prod job on :5100

# Stop/remove old job safely
if (Get-Job -Name vanta_prod -EA SilentlyContinue) {
  Write-Host "Stopping vanta_prod..." -ForegroundColor Cyan
  Get-Job -Name vanta_prod | Stop-Job
  Get-Job -Name vanta_prod -EA SilentlyContinue | Wait-Job -Timeout 3 | Out-Null
  Get-Job -Name vanta_prod -EA SilentlyContinue | Remove-Job -Force
}

# Free port if a stray process owns it
$pid = (Get-NetTCPConnection -LocalPort 5100 -State Listen -EA SilentlyContinue | Select -First 1).OwningProcess
if ($pid) { Write-Host "Freeing :5100 (PID $pid)..." -ForegroundColor Yellow; Stop-Process -Id $pid -Force }

Write-Host "Starting start-prod.ps1..." -ForegroundColor Cyan
.\start-prod.ps1

Write-Host "Checking health..." -ForegroundColor Cyan
Start-Sleep -Seconds 2
try {
  $r = Invoke-WebRequest http://127.0.0.1:5100/__health -UseBasicParsing -TimeoutSec 4
  Write-Host "Health OK: $($r.Content)" -ForegroundColor Green
} catch {
  Write-Host "Health check failed. Tail logs with:" -ForegroundColor Yellow
  Write-Host "Receive-Job -Name vanta_prod -Keep | Select -Last 120" -ForegroundColor Yellow
}
