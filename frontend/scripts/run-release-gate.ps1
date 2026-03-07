param(
  [Parameter(Mandatory = $false)]
  [string]$ProdApiBase = "https://api.staunchbot.com",
  [Parameter(Mandatory = $false)]
  [string]$StagingApiBase = "https://multi-tenant-ai-chatbot-platform-staging.up.railway.app"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (!(Test-Path $pythonExe)) {
  throw "Missing .venv python at: $pythonExe"
}

function Run-Step {
  param(
    [string]$Name,
    [scriptblock]$Action
  )
  Write-Host ""
  Write-Host "=== $Name ===" -ForegroundColor Cyan
  & $Action
  if ($LASTEXITCODE -ne 0) {
    throw "$Name failed with exit code $LASTEXITCODE"
  }
}

Set-Location $repoRoot

Run-Step -Name "Frontend Sanity" -Action { & $pythonExe "frontend/scripts/check_frontend.py" }
Run-Step -Name "Auth Smoke (Prod)" -Action { & $pythonExe "frontend/scripts/auth_smoke.py" --api-base $ProdApiBase }
Run-Step -Name "Auth Smoke (Staging)" -Action { & $pythonExe "frontend/scripts/auth_smoke.py" --api-base $StagingApiBase }
Run-Step -Name "Console Smoke (Prod)" -Action { & $pythonExe "frontend/scripts/console_smoke.py" --api-base $ProdApiBase }
Run-Step -Name "Console Smoke (Staging)" -Action { & $pythonExe "frontend/scripts/console_smoke.py" --api-base $StagingApiBase }

Write-Host ""
Write-Host "Release gate checks passed for production and staging." -ForegroundColor Green
