# Xiaomi S400 Local for Home Assistant

[![Validate](https://github.com/kbpk/xiaomi-s400-homeassistant/actions/workflows/validate.yml/badge.svg)](https://github.com/kbpk/xiaomi-s400-homeassistant/actions/workflows/validate.yml)
[![HACS custom repository](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories/)

[Polska wersja](README.pl.md)

Experimental HACS integration for the Xiaomi Body Composition Scale S400
(`MJTZC01YM`, `yunmai.scales.ms103/ms104/ms107`). Data reception and key storage
happen locally. The Home Assistant integration itself contains no Xiaomi Cloud
client and does not ask for Xiaomi account credentials. A separate lab tool can
request a one-time signature from the Xiaomi backend, which a factory-new S400
with auth version 2 requires.

> [!WARNING]
> The project is in alpha. Auth v2 provisioning was confirmed on an S400 with
> firmware `2.1.1_0006`: the scale returned `REGISTER_OK` and then accepted a
> local login with the token. The first bind requires a one-time credential
> signature from Xiaomi; afterwards data reception and GATT logins are local.
> The purely local provisioner still supports only the older auth version 1.
> Detailed evidence, compatibility limits and the Bluetooth-free analysis are in
> [AUTH_V2.md](research/AUTH_V2.md). The
> [analysis of the official Mi Home APK](research/MIHOME_V2.md) independently
> confirms this order and identifies the missing registration credential.

## Implementation status

- experimental standard-auth version 1 provisioning without OOB via P-256 ECDH,
  HKDF-SHA256 and AES-CCM;
- an auth v2 tool that performs ECDH locally, asks Xiaomi only for the signed
  credential, verifies both signatures locally and was verified on the S400 via
  `REGISTER_OK` and a subsequent token login;
- Bluetooth-free capture analysis and an offline-tested auth v2 credential
  format;
- storing the 16-byte bindkey and the 12-byte token only after the device's
  registration response and a successful login;
- MiBeacon v4/v5 decryption and entities: weight, heart rate, 50 kHz impedance,
  250 kHz impedance, user profile, stabilization and RSSI;
- automatic connection when the scale wakes, token login and local reception of
  live and final measurements from the encrypted CMTP channel;
- redaction of secrets from Home Assistant diagnostics;
- self-contained GATT trace and pairing tools for Raspberry Pi OS/Debian.

The older standard-auth sequence comes from analysis of open source
implementations. It does not match the full version 2 procedure found in the
public SDK. The integration only reports success after a `0x11000000` response
and a successful login, so it will not store random, unagreed keys.

## Installation via HACS

1. Add this repository to HACS as a custom repository of type **Integration**.
2. Download **Xiaomi S400 Local** and restart Home Assistant.
3. Wake the scale and choose
   **Settings → Devices & services → Add integration → Xiaomi S400 Local**.
4. If you already have a bindkey and token, choose `Existing keys`. The token
   enables automatic active GATT reception; without it, reception stays limited
   to FE95 advertisements.

The `Local provisioning` option is currently experimental and only stores keys
when the scale confirms registration and a subsequent login. The token is not
needed for passive advertisements. The automatic active GATT stream requires the
token.

Manual installation means copying the `custom_components/xiaomi_s400_local`
directory into the `custom_components` directory of a Home Assistant instance
and restarting HA.

## First diagnostic trace

Existing captures can be analysed in WSL without a Bluetooth adapter:

```bash
uv run python tools/s400_analyze_trace.py captures/s400-pair*.jsonl
```

The result contains the auth version, information about the key exchange and the
order of `0x13` relative to the registration data. It does not reveal raw frames
or keys.

On Raspberry Pi OS or Debian:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-lab.txt
.venv/bin/python tools/s400_diag.py --duration 60 --output captures/s400-gatt.jsonl
```

Bleak uses the D-Bus BlueZ service. On a typical Raspberry Pi OS a user with
Bluetooth access is enough; if the local D-Bus policy rejects the connection,
run the individual tool through `sudo .venv/bin/python ...`.

The script detects the S400 PID, prints the full GATT database, subscribes to
all `notify`/`indicate` characteristics and writes advertisements and
notifications to JSONL with `0600` permissions. It does not send auth commands.
The `--read` option additionally reads characteristics marked as readable by
GATT.

### Windows / WSL

WSL does not automatically use the Windows Bluetooth stack. Without a passed
through USB adapter, the tools can be run directly through the Windows Python
and Bleak's WinRT backend:

```powershell
$repo = "\\wsl.localhost\Ubuntu\home\kbpk\xiaomi\xiaomi-s400-homeassistant"
uv run --no-project --with-requirements "$repo\requirements-lab.txt" `
  "$repo\tools\s400_diag.py" --duration 60 `
  --output "$repo\captures\s400-gatt.jsonl"
```

The distribution name `Ubuntu` in the path may differ; `wsl -l -v` shows it.
Files on Windows inherit the directory ACL instead of the Unix `0600` mode.

## Standalone local pairing

This applies only to the experimental GET_INFO version 1 path without OOB. The
tested S400 reports version 2 and will receive a message that it is not
supported.

After a factory reset and waking the scale:

```bash
.venv/bin/python tools/s400_pair.py \
  --output private/s400-secrets.json \
  --trace captures/s400-pair.jsonl
```

On Windows, run the same file through `uv` and the WinRT backend:

```powershell
$repo = "\\wsl.localhost\Ubuntu\home\kbpk\xiaomi\xiaomi-s400-homeassistant"
uv run --no-project --with-requirements "$repo\requirements-lab.txt" `
  "$repo\tools\s400_pair.py" `
  --output "$repo\private\s400-secrets.json" `
  --trace "$repo\captures\s400-pair.jsonl"
```

The `--stage-delay` option controls the experimental pause between the scale's
public-key acknowledgement and `SEND_DID` (0 s by default). The trace also
records the completion of every write, the disconnection and the exception, so
that a rejected frame can be told apart from a Bluetooth backend error.

The secrets file has `0600` permissions. The trace contains GATT frames and
public keys, but not the derived token, bindkey or session keys. Do not publish
the `s400-secrets.json` file.

## One-time auth v2 provisioning through Xiaomi

This is the confirmed path for a factory-new S400 with auth v2. The token and
bindkey are still derived locally from ECDH. The MAC, model, token and bindkey
are sent to Xiaomi, exactly as in Mi Home; the server returns the DID, a
certificate and a signature over `DID || bindkey || UTC`. The textual DID is
left-padded with zeros to 20 bytes, exactly as in Mi Home. The script verifies
the credential signature and the certificate against the public root key from
the SDK, requires `REGISTER_OK` and then verifies the token with a local GATT
login.

On Windows with an ASUS USB-BT400, run the tool in a regular PowerShell. The
launcher opens a dedicated Edge profile on the current Xiaomi account page.
Finish the login and any e-mail verification there, and only then return to the
terminal. Before sending the request the provisioner requires the `passToken`
cookie; an unfinished login ends with a local error and does not generate
another code. The login and password are read interactively; the password,
cookies and API responses never end up in arguments, the trace or the result
file:

```powershell
$repo = "\\wsl.localhost\Ubuntu\home\kbpk\xiaomi\xiaomi-s400-homeassistant"
& "$repo\tools\windows\run_s400_xiaomi_pair.ps1" -Region de
```

The region must match the region of the Mi Home account. For an account used in
Poland the usual value is `de`; `cn`, `us`, `ru`, `tw`, `sg`, `in` and `i2` are
also available. The dedicated profile is stored locally in
`%LOCALAPPDATA%\XiaomiS400Provisioner\EdgeProfile`, so cookies survive a restart
after a Xiaomi time limit. The script does not automatically retry a rejected
captcha.

After a success, Xiaomi is no longer needed for the integration to work. In Home
Assistant enter the 32 `bindkey` characters and the 24 `token` characters from
the result file. The tool does not fetch existing keys from the account and does
not compute measurements in the cloud.

A hardware test on 2026-09-21 confirmed the DMTU 242 negotiation, the
multi-frame certificate transfer, the local verification of both signatures, the
`11000000` (`REGISTER_OK`) response and the later `21000000` (`LOGIN_OK`)
response.

Details of the protocol, the state of evidence and the capture workflow are in
[`research/PROTOCOL.md`](research/PROTOCOL.md) and
[`research/CAPTURE.md`](research/CAPTURE.md).

## Development

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

BLE traces and secret files are ignored by Git. The rules for reporting results
and for safely preparing captures are described in
[`CONTRIBUTING.md`](CONTRIBUTING.md).
