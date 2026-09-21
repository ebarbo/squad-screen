from __future__ import annotations

import pytest

from squad_screen.config import reset_settings_cache


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    reset_settings_cache()
    yield
    reset_settings_cache()
