# Third-party notices

The CMTP framing, encryption nonce and S400 CSV payload behavior implemented in
`custom_components/xiaomi_s400_local/active.py` and `crypto.py` were informed by
the public [`nokistin/xiaomi-s400-live`](https://github.com/nokistin/xiaomi-s400-live)
implementation by Nitsikon Mueangsaen, licensed under Apache License 2.0.

This repository does not vendor that project. A copy of Apache License 2.0 is
included in [`LICENSES/Apache-2.0.txt`](LICENSES/Apache-2.0.txt).

The Xiaomi account login and encrypted HTTP envelope in
`tools/xiaomi_cloud.py` were independently implemented against the public
protocol implementation in
[`Bluetooth-Devices/xiaomi-ble`](https://github.com/Bluetooth-Devices/xiaomi-ble),
licensed under Apache License 2.0. That implementation credits
[Piotr Machowski's Xiaomi Cloud Tokens Extractor](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor),
licensed under the MIT License. The corresponding license texts are in
[`LICENSES/Apache-2.0.txt`](LICENSES/Apache-2.0.txt) and
[`LICENSES/MIT-Piotr-Machowski.txt`](LICENSES/MIT-Piotr-Machowski.txt).
