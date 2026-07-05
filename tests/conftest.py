from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_upgrade_check(mocker):
    mocker.patch("mkv_subtitle_translator.cli._check_and_upgrade")
