[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PortfolioFolder,

    [Parameter(Mandatory = $true)]
    [string]$Period,

    [Parameter(Mandatory = $true)]
    [string]$PgdasFolder,

    [string]$OutputDir
)

$ErrorActionPreference = "Stop"
$engineLauncher = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..\..\scripts\invoke-engine.ps1")
)
$arguments = @(
    $PortfolioFolder,
    "--period", $Period,
    "--pgdas-folder", $PgdasFolder
)
if ($OutputDir) {
    $arguments += @("--output-dir", $OutputDir)
}

& $engineLauncher -Command "reconcile-simple-group" -CommandArguments $arguments
exit $LASTEXITCODE
