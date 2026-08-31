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
$runtimeEnvironment = if ($env:FISCAL_INTAKE_ENVIRONMENT) {
    $env:FISCAL_INTAKE_ENVIRONMENT
} else {
    Join-Path $projectRoot ".venv"
}
$env:UV_PROJECT_ENVIRONMENT = $runtimeEnvironment
$extractor = Join-Path $runtimeEnvironment "Scripts\fiscal-document-intake.exe"

if (-not (Test-Path -LiteralPath $extractor -PathType Leaf)) {
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

$arguments = @("extract-content", $Folder)
if ($OutputDir) {
    $arguments += @("--output-dir", $OutputDir)
}

& $extractor @arguments
exit $LASTEXITCODE
