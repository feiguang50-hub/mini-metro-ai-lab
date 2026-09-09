$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = $PSScriptRoot
$Launcher = Join-Path $Root ".venv\Scripts\mini-metro-lab.exe"
$EngineDir = Join-Path $Root ".vendor\python_mini_metro"
$EngineMarker = Join-Path $EngineDir ".mini-metro-engine-commit"
$EngineCommit = "382d7cc65da566ac01d8151921c203c25418eacd"

# Keep Chinese CLI/help output reliable on legacy Windows console code pages.
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
}
catch {
    # Redirected/non-console hosts can reject OutputEncoding changes; Python's
    # explicit UTF-8 environment above is still sufficient for subprocess I/O.
}

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
    }

    & $Launcher @args
    exit $LASTEXITCODE
}
catch {
    Write-Error $_
    exit 1
}
