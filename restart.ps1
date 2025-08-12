# --- Kill anything on port 5000 (preferred: Get-NetTCPConnection) ---
try {
  $pids = (Get-NetTCPConnection -LocalPort 5000 -ErrorAction Stop |
           Select-Object -ExpandProperty OwningProcess) | Sort-Object -Unique
  foreach ($p in $pids) {
    if ($p) { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }
  }
} catch {
  # Fallback to netstat (older systems)
  $net = netstat -ano | Select-String ":5000" | ForEach-Object { ($_ -split "\s+")[-1] } |
         Sort-Object -Unique
  foreach ($p in $net) {
    if ($p -match "^\d+$") { taskkill /F /PID $p | Out-Null }
  }
}

# --- Also stop any stray python servers (optional safety) ---
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force

# --- Clear ONLY project __pycache__ (skip venv) ---
Get-ChildItem -Recurse -Directory -Filter "__pycache__" |
  Where-Object { $_.FullName -notlike "*\venv\*" } |
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# --- Auto-open browser in 1s (in parallel) ---
Start-Job { Start-Sleep -Seconds 1; Start-Process "http://127.0.0.1:5000" } | Out-Null

# --- Start Flask app in debug (auto-reload) ---
# Make sure app.py ends with: app.run(host="0.0.0.0", port=5000, debug=True)
python app.py
