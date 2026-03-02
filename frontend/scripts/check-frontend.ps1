$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (!(Test-Path $pythonExe)) {
  throw "Missing .venv python at: $pythonExe"
}

Set-Location $repoRoot

& $pythonExe "frontend/scripts/check_frontend.py"
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

node --check "frontend/chat-widget.js"
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

Write-Host "[OK] Frontend checks passed."
