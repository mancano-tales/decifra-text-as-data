# Start both local development servers from this checkout's own environment.
param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173
)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot '.venv/Scripts/python.exe'
$vite = Join-Path $repoRoot 'frontend/node_modules/vite/bin/vite.js'
if (!(Test-Path -LiteralPath $python)) { throw "Create this checkout's .venv and install .[dev] first." }
if (!(Test-Path -LiteralPath $vite)) { throw "Run npm ci in frontend first." }
$node = (Get-Command node -ErrorAction Stop).Source
$logDir = Join-Path $repoRoot 'data/dev-logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$oldApiBase = $env:VITE_API_BASE
$env:VITE_API_BASE = "http://localhost:$BackendPort"
$backend = $null
$frontend = $null
try {
    $backend = Start-Process -PassThru -WindowStyle Hidden -FilePath $python `
        -ArgumentList '-m', 'uvicorn', 'text_as_data.app:app', '--port', "$BackendPort" `
        -WorkingDirectory $repoRoot `
        -RedirectStandardOutput (Join-Path $logDir "$stamp-backend.log") `
        -RedirectStandardError (Join-Path $logDir "$stamp-backend-error.log")
    $frontend = Start-Process -PassThru -WindowStyle Hidden -FilePath $node `
        -ArgumentList "`"$vite`"", '--port', "$FrontendPort", '--strictPort' `
        -WorkingDirectory (Join-Path $repoRoot 'frontend') `
        -RedirectStandardOutput (Join-Path $logDir "$stamp-frontend.log") `
        -RedirectStandardError (Join-Path $logDir "$stamp-frontend-error.log")
    Write-Host "Decifra backend: http://localhost:$BackendPort"
    Write-Host "Decifra frontend: http://localhost:$FrontendPort"
    Write-Host "Logs: $logDir"
    Write-Host 'Press Ctrl+C to stop both servers.'
    while (!$backend.HasExited -and !$frontend.HasExited) {
        Start-Sleep -Milliseconds 300
        $backend.Refresh()
        $frontend.Refresh()
    }
    throw "A development server exited. Check the logs in $logDir."
} finally {
    foreach ($server in @($frontend, $backend)) {
        if ($null -ne $server -and !$server.HasExited) {
            Stop-Process -Id $server.Id -ErrorAction SilentlyContinue
        }
    }
    $env:VITE_API_BASE = $oldApiBase
}
