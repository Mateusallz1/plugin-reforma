[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("validate", "extract-content", "review-acquisitions", "review-revenue", "reconcile-simple-revenue", "reconcile-simple-group", "review-counterparties", "plan-credit-simulation", "planning-status", "review-portfolio", "approve-portfolio-group", "export-portfolio-review", "process-portfolio-periods")]
    [string]$Command,

    [string[]]$CommandArguments = @()
)

$ErrorActionPreference = "Stop"
$pluginRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$projectRoot = Join-Path $pluginRoot "engine"
$manifestPath = Join-Path $pluginRoot ".codex-plugin\plugin.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Manifesto do plugin ausente em: $manifestPath"
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$runtimeEnvironment = if ($env:FISCAL_INTAKE_ENVIRONMENT) {
    $env:FISCAL_INTAKE_ENVIRONMENT
} else {
    $localDataRoot = [Environment]::GetFolderPath("LocalApplicationData")
    Join-Path $localDataRoot (
        "Codex\plugins\{0}\{1}\engine" -f $manifest.name, $manifest.version
    )
}
$env:UV_PROJECT_ENVIRONMENT = $runtimeEnvironment
$engine = Join-Path $runtimeEnvironment "Scripts\fiscal-document-intake.exe"

if (-not (Test-Path -LiteralPath (Join-Path $projectRoot "pyproject.toml") -PathType Leaf)) {
    throw "Motor de planejamento ausente em: $projectRoot"
}

if (-not (Test-Path -LiteralPath $engine -PathType Leaf)) {
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

& $engine $Command @CommandArguments
exit $LASTEXITCODE
