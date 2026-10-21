$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $projectRoot
$env:UV_CACHE_DIR = Join-Path $projectRoot '.tools\uv-cache'
function Assert-NativeSuccess { if ($LASTEXITCODE -ne 0) { throw "Previous command failed: $LASTEXITCODE" } }
$uvPath = Join-Path $projectRoot '.tools\uv\bin\uv.exe'
if (-not (Test-Path $uvPath)) {
    python -m pip install --target .tools/uv uv==0.13.1
    Assert-NativeSuccess
}
& $uvPath python install 3.12.15 --install-dir .tools/python --no-bin
Assert-NativeSuccess
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    & $uvPath venv --python .tools/python/cpython-3.12.15-windows-x86_64-none/python.exe .venv
    Assert-NativeSuccess
}
if (Test-Path 'agent\requirements-repro.lock') {
    & $uvPath pip sync --python .venv/Scripts/python.exe agent/requirements-repro.lock
} else {
    & $uvPath pip install --python .venv/Scripts/python.exe -r agent/requirements.txt -c agent/constraints-repro.txt
}
Assert-NativeSuccess
Push-Location front/clinical_cds
try {
    npm.cmd ci --no-audit --no-fund
    Assert-NativeSuccess
} finally { Pop-Location }
Write-Host 'Dependencies ready. Copy agent/.env.example to agent/.env and enter your own key.'
