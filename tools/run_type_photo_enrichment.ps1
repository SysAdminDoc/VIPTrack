[CmdletBinding()]
param(
    [int]$Limit = 500,
    [switch]$AllTypes,
    [switch]$DryRun
)

# Deterministic, resumable workflow for the local aircraft-type photo catalog.
# The Python downloader prefers data/aircraft/types.json, skips existing JPGs,
# and atomically updates assets/type_photos/manifest.json after each success.
# Use -AllTypes only when intentionally expanding beyond the normal 500-type
# catalog; use -DryRun to inspect the ordered work list without network calls.

$repoRoot = Split-Path -Parent $PSScriptRoot
$downloader = Join-Path $repoRoot 'download-type-photos.py'
if (-not (Test-Path -LiteralPath $downloader)) {
    throw "Downloader not found: $downloader"
}
if ($Limit -lt 1 -and -not $AllTypes) {
    throw 'Limit must be at least 1 unless -AllTypes is supplied.'
}

$arguments = @($downloader, '--types-only', '--resume')
if ($AllTypes) {
    $arguments += '--all-types'
} else {
    $arguments += @('--limit', $Limit.ToString())
}
if ($DryRun) {
    $arguments += '--dry-run'
}

& python @arguments
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
