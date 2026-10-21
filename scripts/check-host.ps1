$ErrorActionPreference = 'Stop'
Write-Host 'WSL version:'
& wsl.exe --version
$wslResult = $LASTEXITCODE
$dockerCommand = Get-Command docker.exe -ErrorAction SilentlyContinue
$dockerPath = if ($dockerCommand) { $dockerCommand.Source } else { $null }
if (-not $dockerPath) {
    foreach ($candidate in @(
        'C:\Program Files\Docker\Docker\resources\bin\docker.exe',
        "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe"
    )) {
        if (Test-Path -LiteralPath $candidate) { $dockerPath = $candidate; break }
    }
}
if (-not $dockerPath) { throw 'Docker CLI was not found.' }
Write-Host 'Docker client and engine:'
& $dockerPath version
$dockerResult = $LASTEXITCODE
Write-Host 'Docker Compose:'
& $dockerPath compose version
$composeResult = $LASTEXITCODE
if ($wslResult -ne 0 -or $dockerResult -ne 0 -or $composeResult -ne 0) {
    Write-Host 'Host is not ready yet. Reboot if requested, then start Docker Desktop and wait for its engine.'
    exit 1
}
Write-Host 'Host prerequisites are ready.'
