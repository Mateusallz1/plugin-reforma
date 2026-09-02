[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Folder,

    [string]$Scenario,

    [string]$OutputDir,

    [switch]$MeetingReport
)

$ErrorActionPreference = "Stop"
$engineLauncher = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..\..\scripts\invoke-engine.ps1")
)
$defaultScenario = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\references\credit-scenario-v1.json")
)
$scenarioPath = if ($Scenario) { $Scenario } else { $defaultScenario }
$arguments = @($Folder, "--scenario", $scenarioPath)
if ($OutputDir) {
    $arguments += @("--output-dir", $OutputDir)
}
if ($MeetingReport) {
    $arguments += "--meeting-report"
}

& $engineLauncher -Command "plan-credit-simulation" -CommandArguments $arguments
exit $LASTEXITCODE
