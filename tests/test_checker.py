from __future__ import annotations

from pathlib import Path

import pytest
import requests

from repoman import checker as checker_module
from repoman.checker import Checker
from repoman.models import AvailabilityStatus, FileFormat, Repository


def _make_repo(uri: str = "https://packages.example.com/ubuntu", is_ppa: bool = False) -> Repository:
    repo = Repository(
        source_file=Path("/etc/apt/sources.list.d/test.sources"),
        file_format=FileFormat.DEB822,
        types=["deb"],
        uris=[uri],
        suites=["noble"],
        components=["main"],
        enabled=True,
        description=None,
        signed_by=None,
    )
    return repo


@pytest.fixture(autouse=True)
def reset_network(monkeypatch):
    """Reset global network-failed state before each test."""
    checker_module.reset_network_state()
    yield
    checker_module.reset_network_state()


class TestCheckerHttp:
    def test_available_on_200(self, mocker):
        mock_head = mocker.patch("repoman.checker.requests.head")
        mock_head.return_value.status_code = 200
        c = Checker()
        result = c.check(_make_repo(), "noble")
        assert result == AvailabilityStatus.AVAILABLE

    def test_unavailable_on_404(self, mocker):
        mock_head = mocker.patch("repoman.checker.requests.head")
        mock_head.return_value.status_code = 404
        c = Checker()
        result = c.check(_make_repo(), "noble")
        assert result == AvailabilityStatus.UNAVAILABLE

    def test_unknown_on_other_status(self, mocker):
        mock_head = mocker.patch("repoman.checker.requests.head")
        mock_head.return_value.status_code = 403
        c = Checker()
        result = c.check(_make_repo(), "noble")
        assert result == AvailabilityStatus.UNKNOWN

    def test_timeout_sets_network_failed(self, mocker):
        mocker.patch(
            "repoman.checker.requests.head",
            side_effect=requests.exceptions.Timeout(),
        )
        c = Checker()
        result = c.check(_make_repo(), "noble")
        assert result == AvailabilityStatus.UNKNOWN
        assert checker_module._network_failed is True

    def test_connection_error_sets_network_failed(self, mocker):
        mocker.patch(
            "repoman.checker.requests.head",
            side_effect=requests.exceptions.ConnectionError("DNS failure"),
        )
        c = Checker()
        result = c.check(_make_repo(), "noble")
        assert result == AvailabilityStatus.UNKNOWN
        assert checker_module._network_failed is True

    def test_subsequent_checks_skipped_after_failure(self, mocker):
        mock_head = mocker.patch("repoman.checker.requests.head")
        mock_head.side_effect = requests.exceptions.ConnectionError("down")
        c = Checker()
        c.check(_make_repo(), "noble")
        # Second call should not hit requests at all
        mock_head.reset_mock()
        result = c.check(_make_repo(uri="https://other.example.com"), "noble")
        assert result == AvailabilityStatus.UNKNOWN
        mock_head.assert_not_called()

    def test_network_error_message_captured(self, mocker):
        mocker.patch(
            "repoman.checker.requests.head",
            side_effect=requests.exceptions.ConnectionError("Name resolution failed"),
        )
        c = Checker()
        c.check(_make_repo(), "noble")
        assert "Name resolution failed" in checker_module.get_network_error()

    def test_head_url_includes_codename(self, mocker):
        mock_head = mocker.patch("repoman.checker.requests.head")
        mock_head.return_value.status_code = 200
        c = Checker()
        c.check(_make_repo("https://packages.example.com/ubuntu"), "plucky")
        called_url = mock_head.call_args[0][0]
        assert "plucky" in called_url
        assert called_url == "https://packages.example.com/ubuntu/dists/plucky/InRelease"


class TestCheckerSuiteAgnostic:
    def test_suite_agnostic_skips_check(self, mocker):
        mock_head = mocker.patch("repoman.checker.requests.head")
        repo = _make_repo()
        repo.availability = AvailabilityStatus.SUITE_AGNOSTIC
        c = Checker()
        result = c.check(repo, "noble")
        assert result == AvailabilityStatus.SUITE_AGNOSTIC
        mock_head.assert_not_called()


class TestCheckerLaunchpad:
    def _make_ppa_repo(self) -> Repository:
        return Repository(
            source_file=Path("/etc/apt/sources.list.d/ppa.sources"),
            file_format=FileFormat.DEB822,
            types=["deb"],
            uris=["https://ppa.launchpadcontent.net/testowner/testppa/ubuntu"],
            suites=["noble"],
            components=["main"],
            enabled=True,
            description=None,
            signed_by=None,
        )

    def test_available_when_sources_found(self, mocker):
        mock_lp_module = mocker.MagicMock()
        mock_lp = mocker.MagicMock()
        mock_lp_module.Launchpad.login_anonymously.return_value = mock_lp
        mock_archive = mocker.MagicMock()
        mock_archive.getPublishedSources.return_value.total_size = 5
        mock_lp.people.__getitem__.return_value.getPPAByName.return_value = mock_archive
        mocker.patch.dict("sys.modules", {"launchpadlib": mock_lp_module, "launchpadlib.launchpad": mock_lp_module})

        c = Checker()
        result = c._check_launchpad(self._make_ppa_repo(), "noble")
        assert result == AvailabilityStatus.AVAILABLE

    def test_unavailable_when_no_sources(self, mocker):
        mock_lp_module = mocker.MagicMock()
        mock_lp = mocker.MagicMock()
        mock_lp_module.Launchpad.login_anonymously.return_value = mock_lp
        mock_archive = mocker.MagicMock()
        mock_archive.getPublishedSources.return_value.total_size = 0
        mock_lp.people.__getitem__.return_value.getPPAByName.return_value = mock_archive
        mocker.patch.dict("sys.modules", {"launchpadlib": mock_lp_module, "launchpadlib.launchpad": mock_lp_module})

        c = Checker()
        result = c._check_launchpad(self._make_ppa_repo(), "noble")
        assert result == AvailabilityStatus.UNAVAILABLE

    def test_unavailable_on_key_error(self, mocker):
        mock_lp_module = mocker.MagicMock()
        mock_lp = mocker.MagicMock()
        mock_lp_module.Launchpad.login_anonymously.return_value = mock_lp
        mock_lp.people.__getitem__.side_effect = KeyError("not found")
        mocker.patch.dict("sys.modules", {"launchpadlib": mock_lp_module, "launchpadlib.launchpad": mock_lp_module})

        c = Checker()
        result = c._check_launchpad(self._make_ppa_repo(), "noble")
        assert result == AvailabilityStatus.UNAVAILABLE

    def test_network_failed_on_launchpad_exception(self, mocker):
        mock_lp_module = mocker.MagicMock()
        mock_lp_module.Launchpad.login_anonymously.side_effect = Exception("network error")
        mocker.patch.dict("sys.modules", {"launchpadlib": mock_lp_module, "launchpadlib.launchpad": mock_lp_module})

        c = Checker()
        result = c._check_launchpad(self._make_ppa_repo(), "noble")
        assert result == AvailabilityStatus.UNKNOWN
        assert checker_module._network_failed is True


class TestCheckerResetState:
    def test_reset_clears_failure(self, mocker):
        mocker.patch(
            "repoman.checker.requests.head",
            side_effect=requests.exceptions.ConnectionError("down"),
        )
        c = Checker()
        c.check(_make_repo(), "noble")
        assert checker_module._network_failed is True
        checker_module.reset_network_state()
        assert checker_module._network_failed is False
        assert checker_module.get_network_error() == ""
