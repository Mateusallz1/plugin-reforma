[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Plan", "Process")]
    [string]$Action,

    [Parameter(Mandatory = $true)]
    [string]$PortfolioFolder,

    [ValidateRange(1, 4)]
    [int]$Workers = 2,

    [switch]$Force
)

$ErrorActionPreference = "Stop"
$engineLauncher = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..\..\scripts\invoke-engine.ps1")
)
$acquisitionRuleset = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..\revisar-aquisicoes\references\snapshots\cclass-trib-2026-06-22.json")
)
$cfopRuleset = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..\revisar-receitas\references\snapshots\cfop-2026-08-25.json")
)
$analystRules = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..\revisar-receitas\references\rules\revenue-cfop-rules-v1.json")
)
$arguments = @(
    $PortfolioFolder,
    "--acquisition-ruleset", $acquisitionRuleset,
    "--cfop-ruleset", $cfopRuleset,
    "--analyst-rules", $analystRules,
    "--workers", $Workers
)
if ($Action -eq "Plan") {
    $arguments += "--dry-run"
}
if ($Force) {
    $arguments += "--force"
}

& $engineLauncher -Command "process-portfolio-periods" -CommandArguments $arguments
exit $LASTEXITCODE
