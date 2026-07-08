from __future__ import annotations

import base64
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
    def test_version_is_2(self):
        data = json.loads(config_io.save_config([]))
        assert data["version"] == 2

    def test_saved_at_present(self):
        data = json.loads(config_io.save_config([]))
        assert "saved_at" in data

    def test_saved_codename_included(self):
        data = json.loads(config_io.save_config([], current_codename="noble"))
        assert data["saved_codename"] == "noble"

    def test_saved_codename_empty_by_default(self):
        data = json.loads(config_io.save_config([]))
        assert data["saved_codename"] == ""

    def test_includes_all_repo_fields(self):
        repo = _make_repo(architectures=["amd64"], signed_by=None)
        data = json.loads(config_io.save_config([repo]))
        entry = data["repos"][0]
        assert entry["types"] == ["deb"]
        assert entry["uris"] == ["https://ppa.launchpadcontent.net/testowner/testppa/ubuntu"]
        assert entry["suites"] == ["noble"]
        assert entry["components"] == ["main"]
        assert entry["enabled"] is True
        assert entry["description"] == "Test PPA"
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

    def test_key_file_embedded_as_base64(self, tmp_path):
        key_file = tmp_path / "test.gpg"
        key_file.write_bytes(b"\x99\xab\xcd\xef")
        repo = _make_repo(signed_by=str(key_file))
        data = json.loads(config_io.save_config([repo]))
        assert data["repos"][0]["signed_by_content_b64"] == base64.b64encode(b"\x99\xab\xcd\xef").decode()

    def test_missing_key_file_omits_b64(self):
        repo = _make_repo(signed_by="/nonexistent/path.gpg")
        data = json.loads(config_io.save_config([repo]))
        assert "signed_by_content_b64" not in data["repos"][0]

    def test_inline_pgp_key_no_b64(self):
        repo = _make_repo(signed_by="-----BEGIN PGP PUBLIC KEY BLOCK-----\nfakekey\n-----END PGP PUBLIC KEY BLOCK-----")
        data = json.loads(config_io.save_config([repo]))
        assert "signed_by_content_b64" not in data["repos"][0]


class TestLoadConfig:
    def test_roundtrip_save_load(self, tmp_path):
        repo = _make_repo(signed_by=None)
        path = tmp_path / "config.repoman"
        path.write_text(config_io.save_config([repo], current_codename="noble"))
        entries, saved_codename = config_io.load_config(path)
        assert len(entries) == 1
        assert entries[0]["uris"] == repo.uris
        assert entries[0]["enabled"] is True
        assert saved_codename == "noble"

    def test_v2_roundtrip_preserves_key_content(self, tmp_path):
        key_file = tmp_path / "test.gpg"
        key_file.write_bytes(b"\xde\xad\xbe\xef")
        repo = _make_repo(signed_by=str(key_file))
        repoman_path = tmp_path / "state.repoman"
        repoman_path.write_text(config_io.save_config([repo], current_codename="noble"))
        entries, _ = config_io.load_config(repoman_path)
        assert entries[0]["signed_by_content_b64"] == base64.b64encode(b"\xde\xad\xbe\xef").decode()

    def test_v2_returns_saved_codename(self, tmp_path):
        path = tmp_path / "v2.repoman"
        path.write_text(json.dumps({"version": 2, "saved_codename": "mantic", "repos": []}))
        entries, saved_codename = config_io.load_config(path)
        assert entries == []
        assert saved_codename == "mantic"

    def test_v1_returns_none_codename(self, tmp_path):
        path = tmp_path / "v1.repoman"
        path.write_text(json.dumps({"version": 1, "repos": []}))
        entries, saved_codename = config_io.load_config(path)
        assert entries == []
        assert saved_codename is None

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


ALL_KNOWN = ["focal", "jammy", "mantic", "noble", "oracular", "plucky", "questing"]


class TestClassifyRestoreEntry:
    def _entry(self, **overrides):
        base = {
            "uris": ["https://example.com/ubuntu"],
            "suites": ["noble"],
            "components": ["main"],
            "enabled": True,
        }
        base.update(overrides)
        return base

    def _ppa_entry(self, **overrides):
        base = self._entry(uris=["https://ppa.launchpadcontent.net/owner/ppa/ubuntu"])
        base.update(overrides)
        return base

    # --- Suite-agnostic cases ---

    def test_agnostic_builtin_name_restore_as_is(self):
        entry = self._entry(suites=["stable"])
        assert config_io.classify_restore_entry(entry, "jammy", "noble", ALL_KNOWN) == "restore_as_is"

    def test_agnostic_non_alpha_suite_restore_as_is(self):
        entry = self._entry(suites=["focal-security"])
        assert config_io.classify_restore_entry(entry, "jammy", "noble", ALL_KNOWN) == "restore_as_is"

    def test_agnostic_slash_suite_restore_as_is(self):
        entry = self._entry(suites=["noble/updates"])
        assert config_io.classify_restore_entry(entry, "jammy", "noble", ALL_KNOWN) == "restore_as_is"

    def test_all_suites_agnostic_restore_as_is(self):
        entry = self._entry(suites=["stable", "testing"])
        assert config_io.classify_restore_entry(entry, "jammy", "noble", ALL_KNOWN) == "restore_as_is"

    # --- PPA cases ---

    def test_ppa_launchpadcontent_returns_ppa_check(self):
        entry = self._ppa_entry(suites=["noble"])
        assert config_io.classify_restore_entry(entry, "jammy", "noble", ALL_KNOWN) == "ppa_check"

    def test_ppa_launchpad_net_returns_ppa_check(self):
        entry = self._entry(
            uris=["https://ppa.launchpad.net/owner/ppa/ubuntu"],
            suites=["noble"],
        )
        assert config_io.classify_restore_entry(entry, "jammy", "noble", ALL_KNOWN) == "ppa_check"

    # --- Non-PPA codename cases ---

    def test_older_suite_returns_update_suite(self):
        entry = self._entry(suites=["jammy"])
        assert config_io.classify_restore_entry(entry, "jammy", "noble", ALL_KNOWN) == "update_suite"

    def test_same_suite_as_current_returns_update_suite(self):
        entry = self._entry(suites=["noble"])
        assert config_io.classify_restore_entry(entry, "jammy", "noble", ALL_KNOWN) == "update_suite"

    def test_newer_suite_returns_add_disabled(self):
        entry = self._entry(suites=["oracular"])
        assert config_io.classify_restore_entry(entry, "noble", "noble", ALL_KNOWN) == "add_disabled"

    def test_future_suite_returns_add_disabled(self):
        entry = self._entry(suites=["questing"])
        assert config_io.classify_restore_entry(entry, "noble", "noble", ALL_KNOWN) == "add_disabled"

    # --- Edge cases ---

    def test_unknown_suite_returns_restore_as_is(self):
        entry = self._entry(suites=["unknowncodename"])
        assert config_io.classify_restore_entry(entry, "noble", "noble", ALL_KNOWN) == "restore_as_is"

    def test_unknown_current_codename_returns_restore_as_is(self):
        entry = self._entry(suites=["noble"])
        assert config_io.classify_restore_entry(entry, "noble", "unknowncurrent", ALL_KNOWN) == "restore_as_is"

    def test_custom_agnostic_names_respected(self):
        entry = self._entry(suites=["customstable"])
        result = config_io.classify_restore_entry(
            entry,
            "jammy",
            "noble",
            ALL_KNOWN,
            agnostic_names=frozenset(["customstable"]),
        )
        assert result == "restore_as_is"

    def test_empty_suites_restore_as_is(self):
        entry = self._entry(suites=[])
        assert config_io.classify_restore_entry(entry, "jammy", "noble", ALL_KNOWN) == "restore_as_is"

    def test_mixed_agnostic_and_codename_uses_codename_logic(self):
        # Not all suites are agnostic, so falls through to codename check
        entry = self._entry(suites=["noble"])
        assert config_io.classify_restore_entry(entry, "jammy", "noble", ALL_KNOWN) == "update_suite"
