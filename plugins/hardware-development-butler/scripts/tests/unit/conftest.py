"""Conftest for unit tests.

Manages the HARDWARE_BUTLER_DISABLE_PLATFORMIO env var so that:
- By default, PlatformIO detection is disabled (tests don't trigger real compile)
- Tests marked with @pytest.mark.enable_platformio opt back in.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _disable_platformio_by_default(request):
    """Auto-applied: disable PlatformIO unless test opts out via marker."""
    if "enable_platformio" in request.keywords:
        old = os.environ.pop("HARDWARE_BUTLER_DISABLE_PLATFORMIO", None)
        yield
        if old is not None:
            os.environ["HARDWARE_BUTLER_DISABLE_PLATFORMIO"] = old
    else:
        old = os.environ.get("HARDWARE_BUTLER_DISABLE_PLATFORMIO")
        os.environ["HARDWARE_BUTLER_DISABLE_PLATFORMIO"] = "1"
        yield
        if old is None:
            os.environ.pop("HARDWARE_BUTLER_DISABLE_PLATFORMIO", None)
        else:
            os.environ["HARDWARE_BUTLER_DISABLE_PLATFORMIO"] = old
