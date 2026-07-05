from __future__ import annotations

import json
import urllib.error
from io import BytesIO
from subprocess import CalledProcessError

import pytest
import typer

from translate_subs_openrouter.cli import _check_and_upgrade


def _mock_response(mocker, tag_name):
    body = json.dumps({"tag_name": tag_name}).encode()
    mock_resp = mocker.MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__.return_value = mock_resp
    mocker.patch("translate_subs_openrouter.cli.urllib.request.urlopen", return_value=mock_resp)


class TestCheckAndUpgrade:
    def test_skips_when_up_to_date(self, mocker):
        _mock_response(mocker, "v0.1.0")
        run = mocker.patch("translate_subs_openrouter.cli.subprocess.run")
        _check_and_upgrade("0.1.0")
        run.assert_not_called()

    def test_skips_when_local_is_ahead(self, mocker):
        _mock_response(mocker, "v0.1.0")
        run = mocker.patch("translate_subs_openrouter.cli.subprocess.run")
        _check_and_upgrade("0.2.0")
        run.assert_not_called()

    def test_attempts_upgrade_when_behind(self, mocker):
        _mock_response(mocker, "v9.9.9")
        mocker.patch("translate_subs_openrouter.cli.subprocess.run")
        with pytest.raises(typer.Exit):
            _check_and_upgrade("0.1.0")

    def test_falls_back_to_pip_when_uv_tool_upgrade_fails(self, mocker):
        _mock_response(mocker, "v9.9.9")
        run = mocker.patch(
            "translate_subs_openrouter.cli.subprocess.run",
            side_effect=[CalledProcessError(1, "uv"), None],
        )
        with pytest.raises(typer.Exit):
            _check_and_upgrade("0.1.0")
        assert run.call_count == 2

    def test_shows_manual_message_when_all_upgrades_fail(self, mocker):
        _mock_response(mocker, "v9.9.9")
        mocker.patch(
            "translate_subs_openrouter.cli.subprocess.run",
            side_effect=CalledProcessError(1, "uv"),
        )
        _check_and_upgrade("0.1.0")

    def test_returns_silently_on_network_failure(self, mocker):
        mocker.patch(
            "translate_subs_openrouter.cli.urllib.request.urlopen", side_effect=OSError("boom")
        )
        run = mocker.patch("translate_subs_openrouter.cli.subprocess.run")
        _check_and_upgrade("0.1.0")
        run.assert_not_called()

    def test_returns_silently_on_rate_limit(self, mocker):
        error = urllib.error.HTTPError("url", 403, "Forbidden", {}, BytesIO())
        mocker.patch("translate_subs_openrouter.cli.urllib.request.urlopen", side_effect=error)
        run = mocker.patch("translate_subs_openrouter.cli.subprocess.run")
        _check_and_upgrade("0.1.0")
        run.assert_not_called()
