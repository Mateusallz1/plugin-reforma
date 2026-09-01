[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("validate", "extract-content", "review-acquisitions", "review-revenue", "reconcile-simple-revenue", "planning-status", "review-portfolio", "approve-portfolio-group", "export-portfolio-review", "process-portfolio-periods")]
    [string]$Command,

    [string[]]$CommandArguments = @()
)

$ErrorActionPreference = "Stop"
$pluginRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$projectRoot = Join-Path $pluginRoot "engine"
$runtimeEnvironment = if ($env:FISCAL_INTAKE_ENVIRONMENT) {
    $env:FISCAL_INTAKE_ENVIRONMENT
} else {
    Join-Path $projectRoot ".venv"
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
