[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Folder,

    [string]$SimplesRegistry,

    [switch]$MeetingReport
)

$ErrorActionPreference = "Stop"
$engineLauncher = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..\..\scripts\invoke-engine.ps1")
)
$arguments = @($Folder)
if ($SimplesRegistry) {
    $arguments += @("--simples-registry", $SimplesRegistry)
}
if ($MeetingReport) {
    $arguments += "--meeting-report"
}

& $engineLauncher -Command "review-counterparties" -CommandArguments $arguments
exit $LASTEXITCODE
