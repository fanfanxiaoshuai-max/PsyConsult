param([ValidateSet('infra','backend','frontend','stop-infra','status','offline-test')][string]$Component = 'backend')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $projectRoot
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$env:NO_PROXY = ((($env:NO_PROXY -split ',') + @('localhost','127.0.0.1','::1')) | Where-Object { $_ } | Select-Object -Unique) -join ','
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'

if ($Component -in @('infra','stop-infra','status')) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker Desktop is not installed or not in PATH. See docs/REPRODUCTION.md.'
    }
    switch ($Component) {
        'infra' { docker compose -f docker/compose.fusion.yml up -d }
        'stop-infra' { docker compose -f docker/compose.fusion.yml stop }
        'status' { docker compose -f docker/compose.fusion.yml ps }
    }
    exit $LASTEXITCODE
}
if ($Component -eq 'frontend') {
    Set-Location (Join-Path $projectRoot 'front\clinical_cds')
    npm.cmd run dev -- --host 127.0.0.1 --port 5273 --strictPort
    exit $LASTEXITCODE
}
if (-not (Test-Path $pythonPath)) { throw 'Project Python environment is missing.' }
if ($Component -eq 'offline-test') {
    # A temporary test-only value; never write a dummy key to agent/.env.
    $previousKey = $env:DASHSCOPE_API_KEY
    try {
        $env:DASHSCOPE_API_KEY = 'offline-test-no-network'
        & $pythonPath -m pytest -q
        exit $LASTEXITCODE
    } finally { $env:DASHSCOPE_API_KEY = $previousKey }
}
& $pythonPath -c "from dotenv import dotenv_values; v=dotenv_values('agent/.env').get('DASHSCOPE_API_KEY',''); raise SystemExit(0 if v and v.strip() and not v.startswith(('replace','offline-test')) else 'Fill DASHSCOPE_API_KEY in agent/.env first.')"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $pythonPath -m uvicorn app.app_main:app --host 127.0.0.1 --port 5100
exit $LASTEXITCODE
