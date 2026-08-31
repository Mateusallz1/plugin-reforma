[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Folder,

    [string]$OutputDir
)

$ErrorActionPreference = "Stop"
$engineLauncher = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..\..\scripts\invoke-engine.ps1")
)

$arguments = @($Folder)
if ($OutputDir) {
    $arguments += @("--output-dir", $OutputDir)
}

& $engineLauncher -Command "extract-content" -CommandArguments $arguments
exit $LASTEXITCODE
