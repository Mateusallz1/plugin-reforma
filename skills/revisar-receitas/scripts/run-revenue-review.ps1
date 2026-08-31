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
$cfopRuleset = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\references\snapshots\cfop-2026-08-25.json")
)
$analystRules = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\references\rules\revenue-cfop-rules-v1.json")
)
$arguments = @(
    $Folder,
    "--cfop-ruleset",
    $cfopRuleset,
    "--analyst-rules",
    $analystRules
)
if ($OutputDir) {
    $arguments += @("--output-dir", $OutputDir)
}

& $engineLauncher -Command "review-revenue" -CommandArguments $arguments
exit $LASTEXITCODE
