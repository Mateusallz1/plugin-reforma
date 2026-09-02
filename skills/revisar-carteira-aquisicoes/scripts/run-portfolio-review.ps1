[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("List", "Approve", "Export")]
    [string]$Action,

    [Parameter(Mandatory = $true)]
    [string]$PortfolioFolder,

    [int]$Page = 1,
    [int]$PageSize = 10,
    [string]$GroupId,
    [string]$Nature,
    [ValidateSet("ITEM", "COMPANY", "PORTFOLIO")]
    [string]$Scope,
    [string]$ApprovedBy,
    [string]$Note,
    [string]$CompanyRef,
    [string]$OccurrenceRef,
    [string]$RequestId
)

$ErrorActionPreference = "Stop"
$engineLauncher = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..\..\scripts\invoke-engine.ps1")
)
$ruleset = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..\revisar-aquisicoes\references\snapshots\cclass-trib-2026-06-22.json")
)
$cfopRuleset = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..\revisar-receitas\references\snapshots\cfop-2026-08-25.json")
)
$analystRules = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..\revisar-receitas\references\rules\revenue-cfop-rules-v1.json")
)

if ($Action -eq "List") {
    $arguments = @(
        $PortfolioFolder,
        "--page", $Page,
        "--page-size", $PageSize,
        "--ruleset", $ruleset,
        "--cfop-ruleset", $cfopRuleset,
        "--analyst-rules", $analystRules
    )
    & $engineLauncher -Command "review-portfolio" -CommandArguments $arguments
    exit $LASTEXITCODE
}

if ($Action -eq "Export") {
    & $engineLauncher -Command "export-portfolio-review" -CommandArguments @($PortfolioFolder)
    exit $LASTEXITCODE
}

if (-not $GroupId -or -not $Nature -or -not $Scope -or -not $ApprovedBy) {
    throw "Approve exige GroupId, Nature, Scope e ApprovedBy."
}

$arguments = @(
    $PortfolioFolder,
    "--group-id", $GroupId,
    "--nature", $Nature,
    "--scope", $Scope,
    "--approved-by", $ApprovedBy,
    "--ruleset", $ruleset,
    "--cfop-ruleset", $cfopRuleset,
    "--analyst-rules", $analystRules
)
if ($Note) {
    $arguments += @("--note", $Note)
}
if ($CompanyRef) {
    $arguments += @("--company-ref", $CompanyRef)
}
if ($OccurrenceRef) {
    $arguments += @("--occurrence-ref", $OccurrenceRef)
}
if ($RequestId) {
    $arguments += @("--request-id", $RequestId)
}

& $engineLauncher -Command "approve-portfolio-group" -CommandArguments $arguments
exit $LASTEXITCODE
