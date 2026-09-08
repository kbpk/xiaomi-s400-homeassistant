[CmdletBinding(DefaultParameterSetName = "Start")]
param(
    [Parameter(ParameterSetName = "Start")]
    [string]$Avd = "Medium_Phone",

    [Parameter(Mandatory = $true, ParameterSetName = "Start")]
    [ValidatePattern("^(0x)?[0-9a-fA-F]{4}$")]
    [string]$VendorId,

    [Parameter(Mandatory = $true, ParameterSetName = "Start")]
    [ValidatePattern("^(0x)?[0-9a-fA-F]{4}$")]
    [string]$ProductId,

    [Parameter(ParameterSetName = "Start")]
    [switch]$Headless,

    [Parameter(ParameterSetName = "Start")]
    [switch]$BluetoothPassthroughHal,

    [Parameter(Mandatory = $true, ParameterSetName = "ListUsb")]
    [switch]$ListUsb,

    [Parameter(Mandatory = $true, ParameterSetName = "Stop")]
    [switch]$Stop
)

$ErrorActionPreference = "Stop"
$sdk = if ($env:ANDROID_SDK_ROOT) {
    $env:ANDROID_SDK_ROOT
} else {
    Join-Path $env:LOCALAPPDATA "Android\Sdk"
}
$emulator = Join-Path $sdk "emulator\emulator.exe"
$adb = Join-Path $sdk "platform-tools\adb.exe"

if (-not (Test-Path $emulator)) {
    throw "Nie znaleziono Android Emulator: $emulator"
}

if ($ListUsb) {
    & $emulator -list-usb
    exit $LASTEXITCODE
}

if ($Stop) {
    if (-not (Test-Path $adb)) {
        throw "Nie znaleziono ADB: $adb"
    }
    $serials = & $adb devices | Select-String '^emulator-[0-9]+\s+device$' |
        ForEach-Object { ($_ -split '\s+')[0] }
    foreach ($serial in $serials) {
        & $adb -s $serial emu kill
    }
    exit 0
}

$vid = $VendorId -replace '^0x', ''
$pid = $ProductId -replace '^0x', ''

& sc.exe query UsbAssist *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Sterownik UsbAssist nie jest zainstalowany lub uruchomiony."
}

$usbDevices = & $emulator -list-usb 2>&1
$usbDevices | Write-Host
if ($usbDevices -notmatch "VID:PID\s+$vid`:$pid") {
    throw "Emulator nie widzi urządzenia USB $vid`:$pid."
}

$arguments = @(
    "-avd", $Avd,
    "-no-snapshot",
    "-usb-passthrough", "vendorid=0x$vid,productid=0x$pid"
)

if ($BluetoothPassthroughHal) {
    $arguments += @(
        "-prop", "vendor.qemu.preferred.bt.service=passthrough"
    )
}

if ($Headless) {
    $arguments += @("-no-window", "-no-audio")
}

Write-Host "Uruchamiam: $emulator $($arguments -join ' ')"
Write-Warning "Przekazany adapter znika z Windows do czasu zatrzymania emulatora."
& $emulator @arguments
exit $LASTEXITCODE
