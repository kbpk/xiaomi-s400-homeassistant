param(
    [ValidateSet("cn", "de", "i2", "in", "ru", "sg", "tw", "us")]
    [string]$Region = "de"
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

& uv run --python 3.12 --no-project `
    --with-requirements (Join-Path $repo "requirements-lab.txt") `
    (Join-Path $repo "tools\s400_xiaomi_pair.py") `
    --region $Region `
    --output (Join-Path $repo "private\s400-secrets.json") `
    --trace (Join-Path $repo "captures\s400-xiaomi-pair.jsonl")

$exitCode = $LASTEXITCODE
Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "Provisioning completed successfully." -ForegroundColor Green
} else {
    Write-Host "Provisioning failed with exit code $exitCode." -ForegroundColor Red
}
Read-Host "Press Enter to close"
exit $exitCode
