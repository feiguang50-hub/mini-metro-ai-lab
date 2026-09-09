$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$EngineDir = Join-Path $Root ".vendor\python_mini_metro"
$EngineCommit = "382d7cc65da566ac01d8151921c203c25418eacd"
$EngineMarker = Join-Path $EngineDir ".mini-metro-engine-commit"
$UvDir = Join-Path $Root ".tools\uv"
$LocalUv = Join-Path $UvDir "uv.exe"
$VenvDir = Join-Path $Root ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Get-UvExecutable {
    if (Test-Path $LocalUv) {
        return $LocalUv
    }

    Write-Host "-> Installing a project-local uv copy..."
    New-Item -ItemType Directory -Force -Path $UvDir | Out-Null

    $oldInstallDir = $env:UV_INSTALL_DIR
    $oldNoModifyPath = $env:UV_NO_MODIFY_PATH
    $installerPath = Join-Path ([IO.Path]::GetTempPath()) ("uv-installer-" + [Guid]::NewGuid().ToString("N") + ".ps1")
    try {
        $env:UV_INSTALL_DIR = $UvDir
        $env:UV_NO_MODIFY_PATH = "1"
        Invoke-WebRequest -UseBasicParsing -Uri "https://astral.sh/uv/install.ps1" -OutFile $installerPath
        & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $installerPath
        if ($LASTEXITCODE -ne 0) {
            throw "uv installer failed with exit code ${LASTEXITCODE}."
        }
    }
    finally {
        $env:UV_INSTALL_DIR = $oldInstallDir
        $env:UV_NO_MODIFY_PATH = $oldNoModifyPath
        Remove-Item -Force -ErrorAction SilentlyContinue $installerPath
    }

    if (-not (Test-Path $LocalUv)) {
        throw "uv installer finished, but $LocalUv was not created."
    }
    return $LocalUv
}

function Test-EngineCurrent {
    if (-not (Test-Path $EngineMarker)) {
        return $false
    }
    if (-not (Test-Path (Join-Path $EngineDir "requirements-locked.txt"))) {
        return $false
    }
    return ((Get-Content -Raw $EngineMarker).Trim() -eq $EngineCommit)
}

function Install-PinnedEngine {
    if (Test-EngineCurrent) {
        return
    }

    Write-Host "-> Downloading pinned Mini Metro engine $($EngineCommit.Substring(0, 12))..."
    $VendorDir = Join-Path $Root ".vendor"
    New-Item -ItemType Directory -Force -Path $VendorDir | Out-Null

    $Token = [Guid]::NewGuid().ToString("N")
    $Archive = Join-Path ([IO.Path]::GetTempPath()) "mini-metro-engine-$Token.zip"
    $ExtractDir = Join-Path ([IO.Path]::GetTempPath()) "mini-metro-engine-$Token"
    $ArchiveUrl = "https://github.com/yanfengliu/python_mini_metro/archive/$EngineCommit.zip"

    try {
        Invoke-WebRequest -UseBasicParsing -Uri $ArchiveUrl -OutFile $Archive
        New-Item -ItemType Directory -Force -Path $ExtractDir | Out-Null
        Expand-Archive -Path $Archive -DestinationPath $ExtractDir -Force
        $SourceDir = Get-ChildItem -Path $ExtractDir -Directory | Select-Object -First 1
        if ($null -eq $SourceDir) {
            throw "Pinned engine archive did not contain a source directory."
        }
        if (Test-Path $EngineDir) {
            Remove-Item -Recurse -Force $EngineDir
        }
        Move-Item -Path $SourceDir.FullName -Destination $EngineDir
        Set-Content -Path $EngineMarker -Value $EngineCommit -Encoding ascii -NoNewline
    }
    finally {
        Remove-Item -Force -ErrorAction SilentlyContinue $Archive
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $ExtractDir
    }
}

$Uv = Get-UvExecutable
Install-PinnedEngine

if (-not (Test-Path $VenvPython)) {
    Write-Host "-> Creating Python 3.13 environment..."
    Invoke-Checked $Uv "python" "install" "3.13"
    Invoke-Checked $Uv "venv" "--python" "3.13" $VenvDir
}

Write-Host "-> Installing engine dependencies..."
Invoke-Checked $Uv "pip" "install" "--python" $VenvPython "-r" (Join-Path $EngineDir "requirements-locked.txt")

Write-Host "-> Installing Mini Metro AI Lab..."
Invoke-Checked $Uv "pip" "install" "--python" $VenvPython "-e" $Root

Write-Host "OK: Windows environment is ready."
