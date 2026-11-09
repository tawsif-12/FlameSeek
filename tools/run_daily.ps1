param(
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [ValidateSet('run','backfill','publish','status','import-existing')][string]$Command = 'run',
    [int]$Days = 3
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    & $PythonPath -m pipeline.daily $Command --days $Days
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
