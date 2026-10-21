param([ValidateSet('start','stop','status')][string]$Action = 'status')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$stateFile = Join-Path $projectRoot '.tools\local-app.json'
Set-Location $projectRoot
if ($Action -eq 'stop') {
    if (Test-Path $stateFile) {
        $services = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
        foreach ($service in $services) {
            $processInfo = Get-Process -Id $service.pid -ErrorAction SilentlyContinue
            if ($processInfo -and $processInfo.StartTime.ToUniversalTime().Ticks -eq ([datetime]$service.created).ToUniversalTime().Ticks) {
                # The Windows venv launcher can have a child interpreter.
                & taskkill.exe /PID $service.pid /T /F | Out-Null
                Write-Host "Stopped $($service.name)"
            }
        }
    }
    exit 0
}
if ($Action -eq 'status') {
    Get-NetTCPConnection -State Listen -LocalPort 5100,5273 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess
    exit 0
}
if (Get-NetTCPConnection -State Listen -LocalPort 5100,5273 -ErrorAction SilentlyContinue) {
    throw 'Port 5100 or 5273 is already occupied. Use status, or stop this project first.'
}
& '.\.venv\Scripts\python.exe' -c "from dotenv import dotenv_values; v=dotenv_values('agent/.env').get('DASHSCOPE_API_KEY',''); raise SystemExit(0 if v and v.strip() else 'Configure DASHSCOPE_API_KEY in agent/.env first.')"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$env:NO_PROXY = ((($env:NO_PROXY -split ',') + @('localhost','127.0.0.1','::1')) | Where-Object { $_ } | Select-Object -Unique) -join ','
New-Item -ItemType Directory -Force -Path logs,.tools | Out-Null
$services = @()
try {
    $backend = Start-Process -FilePath (Join-Path $projectRoot '.venv\Scripts\python.exe') -ArgumentList '-m uvicorn app.app_main:app --host 127.0.0.1 --port 5100' -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $projectRoot 'logs\backend-process.out.log') -RedirectStandardError (Join-Path $projectRoot 'logs\backend-process.err.log') -PassThru
    $services += [pscustomobject]@{ name='backend'; pid=$backend.Id; created=$backend.StartTime.ToUniversalTime().ToString('o') }
    $frontend = Start-Process -FilePath (Get-Command node.exe).Source -ArgumentList 'node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5273 --strictPort' -WorkingDirectory (Join-Path $projectRoot 'front\clinical_cds') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $projectRoot 'logs\frontend-process.out.log') -RedirectStandardError (Join-Path $projectRoot 'logs\frontend-process.err.log') -PassThru
    $services += [pscustomobject]@{ name='frontend'; pid=$frontend.Id; created=$frontend.StartTime.ToUniversalTime().ToString('o') }
} finally {
    ConvertTo-Json -InputObject @($services) | Set-Content -LiteralPath $stateFile -Encoding utf8
}
Write-Host 'Processes launched. Wait for initialization, then visit http://127.0.0.1:5273.'
