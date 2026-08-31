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
$ruleset = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\references\snapshots\cclass-trib-2026-06-22.json")
)
$arguments = @($Folder, "--ruleset", $ruleset)
if ($OutputDir) {
    $arguments += @("--output-dir", $OutputDir)
}

& $engineLauncher -Command "review-acquisitions" -CommandArguments $arguments
exit $LASTEXITCODE
