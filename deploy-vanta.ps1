param(
  [string]$Message = "Deploy: latest changes"
)

Write-Host "Staging changes..." -ForegroundColor Cyan
git add -A

Write-Host "Committing..." -ForegroundColor Cyan
git commit -m $Message

Write-Host "Ensuring 'origin' remote..." -ForegroundColor Cyan
$remotes = git remote
if (-not ($remotes -match "^origin$")) {
  git remote add origin https://github.com/shohjahonomonboev/vanta_inventory.git
}

Write-Host "Pushing to origin/main..." -ForegroundColor Cyan
git push -u origin main

Write-Host "Done. If Render is set to auto-deploy, it will redeploy now." -ForegroundColor Green
