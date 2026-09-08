# Changelog

All notable changes to this project will be documented in this file.

The project follows [Semantic Versioning](https://semver.org/).

## 0.1.0 - Unreleased

- Add the initial HACS custom integration structure.
- Add encrypted MiBeacon v4/v5 parsing for S400 measurements.
- Add experimental local Mi Home BLE standard-auth registration and login.
- Add standalone BLE diagnostic, pairing and HCI extraction tools.
- Document captures through the device public-key exchange on firmware
  `2.1.1_0006`.

Known limitation: the tested scale does not yet acknowledge the `SEND_DID`
header after ECDH, so end-to-end local provisioning remains incomplete.
