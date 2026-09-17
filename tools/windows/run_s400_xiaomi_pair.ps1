param(
    [ValidateSet("cn", "de", "i2", "in", "ru", "sg", "tw", "us")]
    [string]$Region = "de"
)

$ErrorActionPreference = "Stop"
$repo = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$statusPath = Join-Path $repo "private\s400-last-run.json"
$errorStatusPath = Join-Path $repo "private\s400-last-error.json"
$startedAt = [DateTime]::UtcNow.ToString("o")
$cdpUrl = "http://127.0.0.1:18800"

New-Item -ItemType Directory -Force (Split-Path $statusPath) | Out-Null
@{
    state = "started"
    started_at = $startedAt
    region = $Region
} | ConvertTo-Json | Set-Content -Encoding UTF8 $statusPath

try {
    & (Join-Path $PSScriptRoot "start_s400_edge.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "The dedicated Edge login session did not start."
    }
    Write-Host "Log in to Xiaomi in the dedicated Edge window." -ForegroundColor Cyan
    Write-Host "Return here only after the Xiaomi account page confirms the login."
    Read-Host "Press Enter after browser login"

    & uv run --python 3.12 --no-project `
        --with-requirements (Join-Path $repo "requirements-lab.txt") `
        (Join-Path $repo "tools\s400_xiaomi_pair.py") `
        --region $Region `
        --output (Join-Path $repo "private\s400-secrets.json") `
        --trace (Join-Path $repo "captures\s400-xiaomi-pair.jsonl") `
        --error-status $errorStatusPath `
        --browser-cdp $cdpUrl
    $exitCode = $LASTEXITCODE
} catch {
    Write-Host $_ -ForegroundColor Red
    $exitCode = 1
}
@{
    state = $(if ($exitCode -eq 0) { "succeeded" } else { "failed" })
    started_at = $startedAt
    finished_at = [DateTime]::UtcNow.ToString("o")
    exit_code = $exitCode
    region = $Region
} | ConvertTo-Json | Set-Content -Encoding UTF8 $statusPath
Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "Provisioning completed successfully." -ForegroundColor Green
} else {
    Write-Host "Provisioning failed with exit code $exitCode." -ForegroundColor Red
}
Read-Host "Press Enter to close"
exit $exitCode
