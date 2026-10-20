$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw 'Environnement Python absent. Consultez README.md pour créer .venv et installer le paquet.'
}
Set-Location -LiteralPath $projectRoot
$env:NIS2_DATA_DIR = Join-Path $projectRoot 'data'
& $pythonExe -m nis2_auditor serve

