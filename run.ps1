$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = $PSScriptRoot
$Launcher = Join-Path $Root ".venv\Scripts\mini-metro-lab.exe"
$EngineDir = Join-Path $Root ".vendor\python_mini_metro"
$EngineMarker = Join-Path $EngineDir ".mini-metro-engine-commit"
$EngineCommit = "382d7cc65da566ac01d8151921c203c25418eacd"

function Test-Ready {
    if (-not (Test-Path $Launcher)) {
        return $false
    }
    if (-not (Test-Path $EngineMarker)) {
        return $false
    }
    return ((Get-Content -Raw $EngineMarker).Trim() -eq $EngineCommit)
}

try {
    if (-not (Test-Ready)) {
        & (Join-Path $Root "scripts\bootstrap.ps1")
        if ($LASTEXITCODE -ne 0) {
            throw "Windows bootstrap failed with exit code $LASTEXITCODE."
        }
    }

    & $Launcher @args
    exit $LASTEXITCODE
}
catch {
    Write-Error $_
    exit 1
}
