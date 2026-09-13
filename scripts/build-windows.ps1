#Requires -Version 5.1
<#
.SYNOPSIS
  Install deps, resolve SemVer, and build dist\FolderBackup\FolderBackup.exe
#>
[CmdletBinding()]
param(
    [string]$Version = "",
    [string]$AssemblyVersion = "",
    [string]$InformationalVersion = ""
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

function Get-FallbackVersion {
    try {
        $tag = git describe --tags --abbrev=0 2>$null
        if ($LASTEXITCODE -eq 0 -and $tag) {
            return ($tag.Trim() -replace '^v', '')
        }
    } catch {
    }
    return "0.1.0"
}

function Get-GitVersionVariable {
    param([string]$Name)
    $commands = @(
        @{ Cmd = "dotnet-gitversion"; Args = @("/showvariable", $Name) },
        @{ Cmd = "gitversion"; Args = @("/showvariable", $Name) }
    )
    foreach ($item in $commands) {
        $exe = Get-Command $item.Cmd -ErrorAction SilentlyContinue
        if (-not $exe) { continue }
        $value = & $exe.Source @($item.Args) 2>$null
        if ($LASTEXITCODE -eq 0 -and $value) {
            return ($value | Select-Object -Last 1).ToString().Trim()
        }
    }
    return ""
}

if (-not $Version) {
    $Version = Get-GitVersionVariable -Name "SemVer"
}
if (-not $Version) {
    Write-Host "GitVersion not available; using fallback SemVer."
    $Version = Get-FallbackVersion
}
if (-not $AssemblyVersion) {
    $AssemblyVersion = Get-GitVersionVariable -Name "AssemblySemVer"
}
if (-not $AssemblyVersion) {
    $AssemblyVersion = $Version
}
if (-not $InformationalVersion) {
    $InformationalVersion = Get-GitVersionVariable -Name "InformationalVersion"
}
if (-not $InformationalVersion) {
    $InformationalVersion = $Version
}

Write-Host "Packaging Folder Backup $Version"

python -m pip install --upgrade pip
python -m pip install -e ".[dev,packaging]"

python (Join-Path $Root "packaging\write_version_info.py") `
    --root $Root `
    --semver $Version `
    --assembly-version $AssemblyVersion `
    --informational-version $InformationalVersion

python -m PyInstaller --noconfirm --clean FolderBackup.spec

$exe = Join-Path $Root "dist\FolderBackup\FolderBackup.exe"
if (-not (Test-Path $exe)) {
    throw "Expected output missing: $exe"
}

$zipName = "FolderBackup-$Version-windows-x64.zip"
$zipPath = Join-Path $Root "dist\$zipName"
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}
Compress-Archive -Path (Join-Path $Root "dist\FolderBackup\*") -DestinationPath $zipPath -Force

Write-Host "Built $exe"
Write-Host "Zipped $zipPath"
