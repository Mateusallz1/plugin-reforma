[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Folder,

    [string]$OutputDir
)

$ErrorActionPreference = "Stop"
$projectRoot = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..\validar-base-documental\scripts\motor-planejamento")
)
$cfopRuleset = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\references\snapshots\cfop-2026-08-25.json")
)
$analystRules = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\references\rules\revenue-cfop-rules-v1.json")
)
$runtimeEnvironment = if ($env:FISCAL_INTAKE_ENVIRONMENT) {
    $env:FISCAL_INTAKE_ENVIRONMENT
} else {
    Join-Path $projectRoot ".venv"
}
$env:UV_PROJECT_ENVIRONMENT = $runtimeEnvironment
$reviewer = Join-Path $runtimeEnvironment "Scripts\fiscal-document-intake.exe"

if (-not (Test-Path -LiteralPath $reviewer -PathType Leaf)) {
    Push-Location $projectRoot
    try {
        & uv sync --locked --no-dev --no-progress
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    } finally {
        Pop-Location
    }
}

$arguments = @(
    "review-revenue",
    $Folder,
    "--cfop-ruleset",
    $cfopRuleset,
    "--analyst-rules",
    $analystRules
)
if ($OutputDir) {
    $arguments += @("--output-dir", $OutputDir)
}

& $reviewer @arguments
exit $LASTEXITCODE
