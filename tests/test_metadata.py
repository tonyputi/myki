"""Keep published examples and metadata consistent with the supported HA release."""

import json
from pathlib import Path
import re

from homeassistant.components.automation.config import PLATFORM_SCHEMA
from homeassistant.helpers import config_validation as cv
from homeassistant.util.yaml import load_yaml_dict
import yaml

ROOT = Path(__file__).parent.parent


async def test_readme_yaml_examples(hass):
    blocks = re.findall(r"```yaml\n(.*?)```", (ROOT / "README.md").read_text(), re.DOTALL)
    assert len(blocks) == 3
    for block in blocks:
        data = yaml.safe_load(block)
        if "alias" in data:
            PLATFORM_SCHEMA(data)
        else:
            cv.SCRIPT_SCHEMA([data])


def test_metadata_and_translations():
    integration = ROOT / "custom_components" / "myki"
    manifest = json.loads((integration / "manifest.json").read_text())
    assert manifest["domain"] == "myki"
    assert json.loads((ROOT / "hacs.json").read_text())["homeassistant"] == "2026.11.0"
    strings = json.loads((integration / "strings.json").read_text())
    assert json.loads((integration / "translations" / "en.json").read_text()) == strings
    assert strings.keys() == json.loads((integration / "translations" / "it.json").read_text()).keys()
    assert strings["services"].keys() == load_yaml_dict(integration / "services.yaml").keys()
