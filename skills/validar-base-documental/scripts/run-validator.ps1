[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Folder,

    [string]$OutputDir
)

$ErrorActionPreference = "Stop"
$projectRoot = Join-Path $PSScriptRoot "motor-planejamento"
$runtimeEnvironment = if ($env:FISCAL_INTAKE_ENVIRONMENT) {
    $env:FISCAL_INTAKE_ENVIRONMENT
} else {
    Join-Path $projectRoot ".venv"
}
$env:UV_PROJECT_ENVIRONMENT = $runtimeEnvironment
$validator = Join-Path $runtimeEnvironment "Scripts\fiscal-document-intake.exe"

if (-not (Test-Path -LiteralPath $validator -PathType Leaf)) {
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

$arguments = @("validate", $Folder)
if ($OutputDir) {
    $arguments += @("--output-dir", $OutputDir)
}

& $validator @arguments
exit $LASTEXITCODE
