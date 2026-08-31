[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Folder,

    [Parameter(Mandatory = $true)]
    [string]$PgdasFolder,

    [string]$OutputDir
)

$ErrorActionPreference = "Stop"
$engineLauncher = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..\..\scripts\invoke-engine.ps1")
)
$arguments = @($Folder, "--pgdas-folder", $PgdasFolder)
if ($OutputDir) {
    $arguments += @("--output-dir", $OutputDir)
}

& $engineLauncher -Command "reconcile-simple-revenue" -CommandArguments $arguments
exit $LASTEXITCODE
