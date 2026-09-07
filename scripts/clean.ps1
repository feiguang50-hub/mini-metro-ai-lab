$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Targets = @(
    (Join-Path $Root ".venv"),
    (Join-Path $Root ".vendor"),
    (Join-Path $Root ".tools"),
    (Join-Path $Root "output")
)

foreach ($Target in $Targets) {
    if (Test-Path $Target) {
        Remove-Item -Recurse -Force $Target
    }
}

Write-Host "OK: removed .venv, .vendor, .tools and output; source files were kept."
