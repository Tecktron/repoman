from __future__ import annotations

import csv
from datetime import date
from unittest.mock import patch

import pytest
import requests

from repoman import upgrade_info
from repoman.models import AvailabilityStatus


class TestGetCurrentCodenameAndDisplay:
    def test_returns_codename_from_os_release(self, mocker):
        mocker.patch(
            "platform.freedesktop_os_release",
            return_value={
                "VERSION_CODENAME": "noble",
                "PRETTY_NAME": "Ubuntu 24.04 LTS (Noble Numbat)",
            },
        )
        codename, display = upgrade_info.get_current_codename_and_display()
        assert codename == "noble"
        assert display == "Ubuntu 24.04 LTS (Noble Numbat)"

    def test_uses_ubuntu_codename_key(self, mocker):
        mocker.patch(
            "platform.freedesktop_os_release",
            return_value={
                "UBUNTU_CODENAME": "noble",
                "VERSION_CODENAME": "something_else",
                "PRETTY_NAME": "Ubuntu 24.04",
            },
        )
        codename, _ = upgrade_info.get_current_codename_and_display()
        assert codename == "noble"

    def test_graceful_on_os_error(self, mocker):
        mocker.patch("platform.freedesktop_os_release", side_effect=OSError("not found"))
        codename, display = upgrade_info.get_current_codename_and_display()
        assert codename == ""
        assert display == "Unknown Ubuntu release"


class TestGetUpgradePrompt:
    def test_reads_lts(self, tmp_path):
        f = tmp_path / "release-upgrades"
        f.write_text("[DEFAULT]\nPrompt=lts\n")
        with patch.object(upgrade_info, "_RELEASE_UPGRADES_PATH", f):
            assert upgrade_info.get_upgrade_prompt() == "lts"

    def test_reads_normal(self, tmp_path):
        f = tmp_path / "release-upgrades"
        f.write_text("[DEFAULT]\nPrompt=normal\n")
        with patch.object(upgrade_info, "_RELEASE_UPGRADES_PATH", f):
            assert upgrade_info.get_upgrade_prompt() == "normal"

    def test_reads_never(self, tmp_path):
        f = tmp_path / "release-upgrades"
        f.write_text("[DEFAULT]\nPrompt=never\n")
        with patch.object(upgrade_info, "_RELEASE_UPGRADES_PATH", f):
            assert upgrade_info.get_upgrade_prompt() == "never"

    def test_defaults_to_lts_when_file_missing(self, tmp_path):
        with patch.object(upgrade_info, "_RELEASE_UPGRADES_PATH", tmp_path / "nonexistent"):
            assert upgrade_info.get_upgrade_prompt() == "lts"

    def test_defaults_to_lts_when_key_missing(self, tmp_path):
        f = tmp_path / "release-upgrades"
        f.write_text("[DEFAULT]\n")
        with patch.object(upgrade_info, "_RELEASE_UPGRADES_PATH", f):
            assert upgrade_info.get_upgrade_prompt() == "lts"


class TestParseUbuntuCsv:
    def _write_csv(self, tmp_path, rows):
        f = tmp_path / "ubuntu.csv"
        with f.open("w") as fp:
            writer = csv.DictWriter(
                fp,
                fieldnames=["version", "codename", "series", "created", "release", "eol"],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        return f

    def test_parses_lts_version(self, tmp_path):
        f = self._write_csv(
            tmp_path,
            [
                {
                    "version": "24.04 LTS",
                    "codename": "Noble Numbat",
                    "series": "noble",
                    "created": "2023-10-12",
                    "release": "2024-04-25",
                    "eol": "2029-05-31",
                }
            ],
        )
        with patch.object(upgrade_info, "_DISTRO_INFO_CSV", f):
            results = upgrade_info._parse_ubuntu_csv()
        assert len(results) == 1
        assert results[0]["series"] == "noble"
        assert results[0]["is_lts"] is True

    def test_parses_non_lts(self, tmp_path):
        f = self._write_csv(
            tmp_path,
            [
                {
                    "version": "24.10",
                    "codename": "Oracular Oriole",
                    "series": "oracular",
                    "created": "2024-04-25",
                    "release": "2024-10-10",
                    "eol": "2025-07-10",
                }
            ],
        )
        with patch.object(upgrade_info, "_DISTRO_INFO_CSV", f):
            results = upgrade_info._parse_ubuntu_csv()
        assert results[0]["is_lts"] is False

    def test_sorted_by_release_date(self, tmp_path):
        f = self._write_csv(
            tmp_path,
            [
                {
                    "version": "24.10",
                    "codename": "Oracular",
                    "series": "oracular",
                    "created": "2024-04-25",
                    "release": "2024-10-10",
                    "eol": "2025-07-10",
                },
                {
                    "version": "24.04 LTS",
                    "codename": "Noble",
                    "series": "noble",
                    "created": "2023-10-12",
                    "release": "2024-04-25",
                    "eol": "2029-05-31",
                },
            ],
        )
        with patch.object(upgrade_info, "_DISTRO_INFO_CSV", f):
            results = upgrade_info._parse_ubuntu_csv()
        assert results[0]["series"] == "noble"
        assert results[1]["series"] == "oracular"

    def test_returns_empty_on_missing_csv(self, tmp_path):
        with patch.object(upgrade_info, "_DISTRO_INFO_CSV", tmp_path / "nonexistent.csv"):
            assert upgrade_info._parse_ubuntu_csv() == []

    def test_skips_rows_with_missing_fields(self, tmp_path):
        f = tmp_path / "ubuntu.csv"
        f.write_text(
            "version,codename,series,created,release,eol\n"
            "24.04 LTS,Noble,noble,2023-10-12,,2029-05-31\n"  # missing release date
            "24.10,Oracular,oracular,2024-04-25,2024-10-10,2025-07-10\n"
        )
        with patch.object(upgrade_info, "_DISTRO_INFO_CSV", f):
            results = upgrade_info._parse_ubuntu_csv()
        assert len(results) == 1
        assert results[0]["series"] == "oracular"


class TestGetUpgradeTargets:
    @pytest.fixture(autouse=True)
    def mock_csv(self, mocker):
        releases = [
            {"series": "noble", "version": "24.04 LTS", "date": date(2024, 4, 25), "is_lts": True},
            {"series": "oracular", "version": "24.10", "date": date(2024, 10, 10), "is_lts": False},
            {"series": "plucky", "version": "25.04", "date": date(2025, 4, 17), "is_lts": False},
            {
                "series": "resolute",
                "version": "26.04 LTS",
                "date": date(2026, 4, 23),
                "is_lts": True,
            },
        ]
        mocker.patch.object(upgrade_info, "_parse_ubuntu_csv", return_value=releases)

    def test_lts_prompt_filters_to_lts_only(self):
        targets = upgrade_info.get_upgrade_targets("noble", "lts")
        codenames = [t[0] for t in targets]
        assert "resolute" in codenames
        assert "oracular" not in codenames
        assert "plucky" not in codenames

    def test_normal_prompt_includes_all(self):
        targets = upgrade_info.get_upgrade_targets("noble", "normal")
        codenames = [t[0] for t in targets]
        assert "oracular" in codenames
        assert "plucky" in codenames
        assert "resolute" in codenames

    def test_never_prompt_returns_empty(self):
        assert upgrade_info.get_upgrade_targets("noble", "never") == []

    def test_unknown_current_codename(self):
        assert upgrade_info.get_upgrade_targets("jammy", "lts") == []

    def test_label_format(self):
        targets = upgrade_info.get_upgrade_targets("noble", "normal")
        oracular = next(t for t in targets if t[0] == "oracular")
        assert oracular[1] == "oracular (24.10)"


class TestCheckPpaForCodename:
    def test_returns_available_on_200(self, mocker):
        mock_head = mocker.patch("repoman.upgrade_info.requests.head")
        mock_head.return_value.status_code = 200
        status, error = upgrade_info.check_ppa_for_codename("testowner", "testppa", "noble")
        assert status == AvailabilityStatus.AVAILABLE
        assert error is None

    def test_returns_unavailable_on_404(self, mocker):
        mock_head = mocker.patch("repoman.upgrade_info.requests.head")
        mock_head.return_value.status_code = 404
        status, error = upgrade_info.check_ppa_for_codename("testowner", "testppa", "noble")
        assert status == AvailabilityStatus.UNAVAILABLE
        assert error is None

    def test_returns_unknown_on_other_status(self, mocker):
        mock_head = mocker.patch("repoman.upgrade_info.requests.head")
        mock_head.return_value.status_code = 403
        status, error = upgrade_info.check_ppa_for_codename("testowner", "testppa", "noble")
        assert status == AvailabilityStatus.UNKNOWN
        assert error is not None

    def test_returns_unknown_on_timeout(self, mocker):
        mocker.patch(
            "repoman.upgrade_info.requests.head",
            side_effect=requests.exceptions.Timeout(),
        )
        status, error = upgrade_info.check_ppa_for_codename("testowner", "testppa", "noble")
        assert status == AvailabilityStatus.UNKNOWN
        assert error is not None

    def test_returns_unknown_on_connection_error(self, mocker):
        mocker.patch(
            "repoman.upgrade_info.requests.head",
            side_effect=requests.exceptions.ConnectionError("DNS failure"),
        )
        status, error = upgrade_info.check_ppa_for_codename("testowner", "testppa", "noble")
        assert status == AvailabilityStatus.UNKNOWN
        assert error is not None
        assert "DNS failure" in error

    def test_correct_url_constructed(self, mocker):
        mock_head = mocker.patch("repoman.upgrade_info.requests.head")
        mock_head.return_value.status_code = 200
        upgrade_info.check_ppa_for_codename("myowner", "myppa", "noble")
        called_url = mock_head.call_args[0][0]
        assert called_url == ("https://ppa.launchpadcontent.net/myowner/myppa/ubuntu/dists/noble/InRelease")

    def test_error_message_returned_on_failure(self, mocker):
        mocker.patch(
            "repoman.upgrade_info.requests.head",
            side_effect=requests.exceptions.ConnectionError("Connection refused"),
        )
        status, error = upgrade_info.check_ppa_for_codename("testowner", "testppa", "noble")
        assert error is not None
        assert len(error) > 0
