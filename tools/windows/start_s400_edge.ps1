$ErrorActionPreference = "Stop"

$cdpUrl = "http://127.0.0.1:18800"
$edge = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
$profile = Join-Path $env:LOCALAPPDATA "XiaomiS400Provisioner\EdgeProfile"

if (-not (Test-Path $edge)) {
    throw "Microsoft Edge was not found at $edge"
}

New-Item -ItemType Directory -Force $profile | Out-Null
$arguments = @(
    "--remote-debugging-port=18800"
    "--remote-allow-origins=http://127.0.0.1:18800"
    "--user-data-dir=$profile"
    "--no-first-run"
    "--new-window"
    "https://account.xiaomi.com/"
)
Start-Process -FilePath $edge -ArgumentList $arguments

for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $version = Invoke-RestMethod "$cdpUrl/json/version" -TimeoutSec 1
        Write-Host "CDP ready: $($version.Browser)" -ForegroundColor Green
        exit 0
    } catch {
        Start-Sleep -Seconds 1
    }
}

throw "Edge started, but CDP port 18800 did not become available."
