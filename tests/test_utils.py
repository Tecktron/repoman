from __future__ import annotations

from pathlib import Path

from repoman import utils
from repoman.models import AvailabilityStatus, FileFormat, Repository


def _make_repo(enabled: bool = True, suites: list[str] | None = None) -> Repository:
    return Repository(
        source_file=Path("/etc/apt/sources.list.d/test.sources"),
        file_format=FileFormat.DEB822,
        types=["deb"],
        uris=["https://packages.example.com/ubuntu"],
        suites=suites or ["noble"],
        components=["main"],
        enabled=enabled,
        description=None,
        signed_by=None,
    )


class TestGetCurrentCodename:
    def test_returns_stripped_string(self, mocker):
        mock_run = mocker.patch("repoman.utils.subprocess.run")
        mock_run.return_value.stdout = "noble\n"
        result = utils.get_current_codename()
        assert result == "noble"
        # Check the flag args; the binary path is resolved via shutil.which so may vary
        assert mock_run.call_args[0][0][1:] == ["-cs"]
        assert mock_run.call_args[1] == {"capture_output": True, "text": True}

    def test_strips_trailing_whitespace(self, mocker):
        mock_run = mocker.patch("repoman.utils.subprocess.run")
        mock_run.return_value.stdout = "plucky   \n"
        result = utils.get_current_codename()
        assert result == "plucky"


class TestReposNeedingAttention:
    def test_disabled_repo_flagged(self, mocker):
        mocker.patch("repoman.utils.get_current_codename", return_value="noble")
        repos = [_make_repo(enabled=False)]
        result = utils.repos_needing_attention(repos)
        assert repos[0] in result

    def test_stale_codename_flagged(self, mocker):
        mocker.patch("repoman.utils.get_current_codename", return_value="noble")
        repos = [_make_repo(suites=["jammy"])]
        result = utils.repos_needing_attention(repos)
        assert repos[0] in result

    def test_current_codename_not_flagged(self, mocker):
        mocker.patch("repoman.utils.get_current_codename", return_value="noble")
        repos = [_make_repo(suites=["noble"])]
        result = utils.repos_needing_attention(repos)
        assert result == []

    def test_enabled_suite_agnostic_not_flagged(self, mocker):
        mocker.patch("repoman.utils.get_current_codename", return_value="noble")
        repo = _make_repo(suites=["stable"])
        repo.availability = AvailabilityStatus.SUITE_AGNOSTIC
        result = utils.repos_needing_attention([repo])
        assert result == []

    def test_disabled_suite_agnostic_flagged(self, mocker):
        mocker.patch("repoman.utils.get_current_codename", return_value="noble")
        repo = _make_repo(enabled=False, suites=["stable"])
        repo.availability = AvailabilityStatus.SUITE_AGNOSTIC
        result = utils.repos_needing_attention([repo])
        assert repo in result

    def test_non_alpha_suite_not_flagged(self, mocker):
        mocker.patch("repoman.utils.get_current_codename", return_value="noble")
        # Suites like "noble-updates" contain hyphens — not isalpha(), so skipped
        repo = _make_repo(suites=["noble-updates"])
        result = utils.repos_needing_attention([repo])
        assert result == []

    def test_empty_repos_list(self, mocker):
        mocker.patch("repoman.utils.get_current_codename", return_value="noble")
        assert utils.repos_needing_attention([]) == []

    def test_multiple_suites_any_stale_flags_repo(self, mocker):
        mocker.patch("repoman.utils.get_current_codename", return_value="noble")
        repo = _make_repo(suites=["noble", "jammy"])
        result = utils.repos_needing_attention([repo])
        assert repo in result
