[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Folder,

    [string]$PgdasFolder,

    [string]$OutputDir
)

$ErrorActionPreference = "Stop"
$engineLauncher = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..\..\scripts\invoke-engine.ps1")
)
$arguments = @($Folder)
if ($PgdasFolder) {
    $arguments += @("--pgdas-folder", $PgdasFolder)
}
if ($OutputDir) {
    $arguments += @("--output-dir", $OutputDir)
}

& $engineLauncher -Command "planning-status" -CommandArguments $arguments
exit $LASTEXITCODE
