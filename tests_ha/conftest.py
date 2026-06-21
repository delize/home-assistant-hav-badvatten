"""Real-Home-Assistant tests (pytest-homeassistant-custom-component).

Kept separate from tests/ (which stubs homeassistant) so the two don't clash.
These exercise the actual config/options flow that the stub tests can't reach.
"""

from pathlib import Path
import sys

import pytest

# make `custom_components.hav_badvatten` importable
sys.path.insert(0, str(Path(__file__).parents[1]))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
