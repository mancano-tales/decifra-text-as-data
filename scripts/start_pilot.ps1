# Start the built MVP locally, preserving pilot data between sessions.
param([int]$Port = 8765)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $python)) { throw "Install the project in .venv first (see README)." }
if (!(Test-Path -LiteralPath (Join-Path $repoRoot 'src/text_as_data/static/index.html'))) { throw "Build the frontend first (see README)." }
$pilot = Join-Path $repoRoot 'data/pilot'
$env:DECIFRA_CONFIG_DIR = Join-Path $pilot 'config'
& $python -m text_as_data.cli serve --data-dir $pilot --port $Port
