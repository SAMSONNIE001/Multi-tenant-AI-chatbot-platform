$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (!(Test-Path $pythonExe)) {
  throw "Missing .venv python at: $pythonExe"
}

Set-Location $repoRoot
& $pythonExe -m pytest -q backend/tests
