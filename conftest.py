"""Make the repo root importable and enable custom integrations in tests."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
