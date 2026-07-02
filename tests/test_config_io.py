from __future__ import annotations

import json
from pathlib import Path

import pytest

from repoman import config_io
from repoman.models import FileFormat, Repository


def _make_repo(**overrides) -> Repository:
    defaults = {
        "source_file": Path("/etc/apt/sources.list.d/test.sources"),
        "file_format": FileFormat.DEB822,
        "types": ["deb"],
        "uris": ["https://ppa.launchpadcontent.net/testowner/testppa/ubuntu"],
        "suites": ["noble"],
        "components": ["main"],
        "enabled": True,
        "description": "Test PPA",
        "signed_by": "/usr/share/keyrings/testowner-testppa.gpg",
    }
    defaults.update(overrides)
    return Repository(**defaults)


class TestSaveConfig:
    def test_version_is_1(self):
        data = json.loads(config_io.save_config([]))
        assert data["version"] == 1

    def test_saved_at_present(self):
        data = json.loads(config_io.save_config([]))
        assert "saved_at" in data

    def test_includes_all_repo_fields(self):
        repo = _make_repo(architectures=["amd64"])
        data = json.loads(config_io.save_config([repo]))
        entry = data["repos"][0]
        assert entry["types"] == ["deb"]
        assert entry["uris"] == ["https://ppa.launchpadcontent.net/testowner/testppa/ubuntu"]
        assert entry["suites"] == ["noble"]
        assert entry["components"] == ["main"]
        assert entry["enabled"] is True
        assert entry["description"] == "Test PPA"
        assert entry["signed_by"] == "/usr/share/keyrings/testowner-testppa.gpg"
        assert entry["architectures"] == ["amd64"]
        assert entry["source_file"] == "/etc/apt/sources.list.d/test.sources"

    def test_optional_fields_nullable(self):
        repo = _make_repo(description=None, signed_by=None)
        data = json.loads(config_io.save_config([repo]))
        entry = data["repos"][0]
        assert entry["description"] is None
        assert entry["signed_by"] is None

    def test_multiple_repos(self):
        repos = [_make_repo(), _make_repo(uris=["https://example.com/ubuntu"])]
        data = json.loads(config_io.save_config(repos))
        assert len(data["repos"]) == 2

    def test_disabled_repo_serialised(self):
        repo = _make_repo(enabled=False)
        data = json.loads(config_io.save_config([repo]))
        assert data["repos"][0]["enabled"] is False

    def test_empty_repo_list(self):
        data = json.loads(config_io.save_config([]))
        assert data["repos"] == []


class TestLoadConfig:
    def test_roundtrip_save_load(self, tmp_path):
        repo = _make_repo()
        path = tmp_path / "config.repoman"
        path.write_text(config_io.save_config([repo]))
        entries = config_io.load_config(path)
        assert len(entries) == 1
        assert entries[0]["uris"] == repo.uris
        assert entries[0]["enabled"] is True

    def test_raises_on_bad_version(self, tmp_path):
        path = tmp_path / "bad.repoman"
        path.write_text(json.dumps({"version": 99, "repos": []}))
        with pytest.raises(ValueError, match="Unsupported config version"):
            config_io.load_config(path)

    def test_raises_on_missing_version(self, tmp_path):
        path = tmp_path / "bad.repoman"
        path.write_text(json.dumps({"repos": []}))
        with pytest.raises(ValueError, match="Unsupported config version"):
            config_io.load_config(path)

    def test_raises_on_invalid_json(self, tmp_path):
        path = tmp_path / "bad.repoman"
        path.write_text("not json {{{")
        with pytest.raises(json.JSONDecodeError):
            config_io.load_config(path)

    def test_raises_on_missing_repos_key(self, tmp_path):
        path = tmp_path / "bad.repoman"
        path.write_text(json.dumps({"version": 1}))
        with pytest.raises(KeyError):
            config_io.load_config(path)


class TestMatchRepos:
    def _live(self, uri="https://ppa.launchpadcontent.net/testowner/testppa/ubuntu", enabled=True):
        return _make_repo(uris=[uri], enabled=enabled)

    def test_matches_by_uri(self):
        live = self._live()
        saved = [{"uris": [live.uris[0]], "enabled": True}]
        matched, missing = config_io.match_repos(saved, [live])
        assert len(matched) == 1
        assert matched[0][1] is live
        assert missing == []

    def test_unmatched_uri_goes_to_missing(self):
        live = self._live()
        saved = [{"uris": ["https://other.example.com/ubuntu"], "enabled": True}]
        matched, missing = config_io.match_repos(saved, [live])
        assert matched == []
        assert len(missing) == 1

    def test_partial_match(self):
        live1 = self._live("https://a.example.com/ubuntu")
        live2 = self._live("https://b.example.com/ubuntu")
        saved = [
            {"uris": ["https://a.example.com/ubuntu"], "enabled": True},
            {"uris": ["https://c.example.com/ubuntu"], "enabled": True},
        ]
        matched, missing = config_io.match_repos(saved, [live1, live2])
        assert len(matched) == 1
        assert len(missing) == 1

    def test_empty_saved_returns_empty(self):
        matched, missing = config_io.match_repos([], [self._live()])
        assert matched == []
        assert missing == []

    def test_empty_live_all_missing(self):
        saved = [{"uris": ["https://example.com/ubuntu"], "enabled": True}]
        matched, missing = config_io.match_repos(saved, [])
        assert matched == []
        assert len(missing) == 1

    def test_entry_with_no_uris_is_missing(self):
        saved = [{"uris": [], "enabled": True}]
        _, missing = config_io.match_repos(saved, [self._live()])
        assert len(missing) == 1

    def test_repo_with_no_uris_not_indexed(self):
        live = _make_repo(uris=[])
        saved = [{"uris": ["https://example.com/ubuntu"], "enabled": True}]
        matched, missing = config_io.match_repos(saved, [live])
        assert matched == []
        assert len(missing) == 1


class TestEntryToRepository:
    def _entry(self, **overrides):
        base = {
            "types": ["deb"],
            "uris": ["https://ppa.launchpadcontent.net/testowner/testppa/ubuntu"],
            "suites": ["noble"],
            "components": ["main"],
            "enabled": True,
            "description": "Test PPA",
            "signed_by": "/usr/share/keyrings/test.gpg",
            "source_file": "/etc/apt/sources.list.d/testowner-testppa.sources",
        }
        base.update(overrides)
        return base

    def test_reconstructs_all_fields(self):
        entry = self._entry(architectures=["amd64"])
        repo = config_io.entry_to_repository(entry)
        assert repo.uris == ["https://ppa.launchpadcontent.net/testowner/testppa/ubuntu"]
        assert repo.suites == ["noble"]
        assert repo.components == ["main"]
        assert repo.enabled is True
        assert repo.description == "Test PPA"
        assert repo.signed_by == "/usr/share/keyrings/test.gpg"
        assert repo.architectures == ["amd64"]
        assert repo.source_file == Path("/etc/apt/sources.list.d/testowner-testppa.sources")

    def test_architectures_defaults_to_empty_when_missing(self):
        """Old .repoman files without 'architectures' key load without error."""
        entry = self._entry()
        repo = config_io.entry_to_repository(entry)
        assert repo.architectures == []

    def test_sets_file_format_to_deb822(self):
        repo = config_io.entry_to_repository(self._entry())
        assert repo.file_format == FileFormat.DEB822

    def test_defaults_types_to_deb_when_missing(self):
        entry = self._entry()
        del entry["types"]
        repo = config_io.entry_to_repository(entry)
        assert repo.types == ["deb"]

    def test_optional_fields_none(self):
        entry = self._entry(description=None, signed_by=None)
        repo = config_io.entry_to_repository(entry)
        assert repo.description is None
        assert repo.signed_by is None

    def test_disabled_repo_reconstructed(self):
        repo = config_io.entry_to_repository(self._entry(enabled=False))
        assert repo.enabled is False
