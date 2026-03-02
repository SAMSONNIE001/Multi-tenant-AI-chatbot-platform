$ErrorActionPreference = "Stop"

param(
  [Parameter(Mandatory = $false)]
  [string]$ApiBase = "http://localhost:8000"
)

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (!(Test-Path $pythonExe)) {
  throw "Missing .venv python at: $pythonExe"
}

Set-Location $repoRoot

& $pythonExe "frontend/scripts/console_smoke.py" --api-base $ApiBase
exit $LASTEXITCODE
