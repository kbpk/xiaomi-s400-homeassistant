# Contributing

Contributions should distinguish behavior proven by source code or a packet
capture from hypotheses that still need a device test. Include the scale PID,
firmware version, operating system and Bluetooth backend with every protocol
report.

## Development setup

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Commits and pull requests

Use [Conventional Commits](https://www.conventionalcommits.org/) for every
commit and pull-request title. Typical types in this repository are `feat`,
`fix`, `docs`, `test`, `refactor`, `ci`, `build` and `chore`.

Examples:

```text
feat(pairing): handle the S400 bind-confirm frame
fix(parser): reject a truncated capability field
docs(capture): add AAOS passthrough verification
```

The pull-request title is checked automatically because accepted changes are
intended to be squash-merged using that title.

The reusable protocol code lives in
`custom_components/xiaomi_s400_local`. Standalone tools load the same modules,
so protocol changes should not be duplicated under `tools`.

## Captures

Do not commit raw captures or credential files. They can contain MAC addresses,
device identifiers, public protocol transcripts, bindkeys and tokens. Before
sharing a minimized trace:

1. Remove unrelated Bluetooth and network traffic.
2. Replace personal device identifiers consistently.
3. Confirm that no bindkey, token or session key is present.
4. Describe the exact reset and capture procedure in the issue.

See `research/CAPTURE.md` for capture commands and `research/PROTOCOL.md` for
the current evidence boundary.
