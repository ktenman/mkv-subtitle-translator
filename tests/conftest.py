from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_upgrade_check(mocker):
    mocker.patch("translate_subs_openrouter.cli._check_and_upgrade")
