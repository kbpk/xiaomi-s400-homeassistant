from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "xiaomi_s400_local"


def _read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def test_hacs_and_manifest_structure() -> None:
    hacs = _read_json(ROOT / "hacs.json")
    manifest = _read_json(INTEGRATION / "manifest.json")

    assert hacs["name"] == manifest["name"]
    assert manifest["domain"] == INTEGRATION.name
    assert manifest["config_flow"] is True
    assert manifest["version"]
    assert manifest["codeowners"]
    assert (INTEGRATION / "config_flow.py").is_file()
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)
    assert manifest["version"] == project["project"]["version"]


def test_translation_shapes_match_strings() -> None:
    strings = _read_json(INTEGRATION / "strings.json")
    for language in ("en", "pl"):
        translation = _read_json(INTEGRATION / "translations" / f"{language}.json")
        assert translation.keys() == strings.keys()
        assert translation["config"].keys() == strings["config"].keys()
        assert translation["entity"].keys() == strings["entity"].keys()
