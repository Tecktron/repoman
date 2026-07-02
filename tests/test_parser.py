from __future__ import annotations

from pathlib import Path

import pytest

import repoman.parser as parser_module
from repoman.models import AvailabilityStatus, FileFormat
from repoman.parser import _BUILTIN_AGNOSTIC, Parser, _is_suite_agnostic, _load_agnostic_names

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def parser(tmp_path):
    """Parser pointed at a writable temp directory populated with fixtures."""
    return Parser(sources_dir=tmp_path)


def _copy(src: Path, dst_dir: Path) -> Path:
    dest = dst_dir / src.name
    dest.write_text(src.read_text())
    return dest


class TestDeb822Parsing:
    def test_ppa_sources(self, parser, tmp_path):
        _copy(FIXTURES / "sample_ppa.sources", tmp_path)
        repos = parser.load_all()
        assert len(repos) == 1
        r = repos[0]
        assert r.file_format == FileFormat.DEB822
        assert r.is_ppa is True
        assert r.ppa_owner == "testowner"
        assert r.ppa_name == "testppa"
        assert r.enabled is True
        assert r.description == "Test PPA for unit tests"
        assert r.suites == ["noble"]
        assert r.availability == AvailabilityStatus.UNKNOWN

    def test_third_party_sources(self, parser, tmp_path):
        _copy(FIXTURES / "sample_third_party.sources", tmp_path)
        repos = parser.load_all()
        assert len(repos) == 1
        r = repos[0]
        assert r.is_ppa is False
        assert r.components == ["main", "contrib"]
        assert r.signed_by == "/usr/share/keyrings/example.gpg"

    def test_suite_agnostic_sources(self, parser, tmp_path):
        _copy(FIXTURES / "sample_suite_agnostic.sources", tmp_path)
        repos = parser.load_all()
        assert len(repos) == 1
        assert repos[0].availability == AvailabilityStatus.SUITE_AGNOSTIC

    def test_disabled_sources(self, parser, tmp_path):
        _copy(FIXTURES / "sample_disabled.sources", tmp_path)
        repos = parser.load_all()
        assert len(repos) == 1
        assert repos[0].enabled is False

    def test_skips_non_source_files(self, parser, tmp_path):
        (tmp_path / "some_file.bak").write_text("deb https://example.com noble main")
        (tmp_path / "some_file.list.save").write_text("deb https://example.com noble main")
        repos = parser.load_all()
        assert repos == []

    def test_sorted_by_display_name(self, parser, tmp_path):
        _copy(FIXTURES / "sample_ppa.sources", tmp_path)
        _copy(FIXTURES / "sample_third_party.sources", tmp_path)
        repos = parser.load_all()
        names = [r.display_name for r in repos]
        assert names == sorted(names, key=str.lower)

    def test_missing_sources_dir_returns_empty(self, tmp_path):
        p = Parser(sources_dir=tmp_path / "nonexistent")
        assert p.load_all() == []

    def test_description_none_when_absent(self, parser, tmp_path):
        (tmp_path / "nodesc.sources").write_text(
            "Types: deb\nURIs: https://example.com\nSuites: noble\nComponents: main\nEnabled: yes\n"
        )
        repos = parser.load_all()
        assert repos[0].description is None

    def test_display_name_falls_back_to_uri(self, parser, tmp_path):
        (tmp_path / "nodesc.sources").write_text(
            "Types: deb\nURIs: https://example.com\nSuites: noble\nComponents: main\nEnabled: yes\n"
        )
        repos = parser.load_all()
        assert repos[0].display_name == "https://example.com"


class TestOneLineParsing:
    def test_legacy_list(self, parser, tmp_path):
        _copy(FIXTURES / "sample_legacy.list", tmp_path)
        repos = parser.load_all()
        assert len(repos) == 2  # one enabled, one disabled (# deb line)
        enabled = [r for r in repos if r.enabled]
        disabled = [r for r in repos if not r.enabled]
        assert len(enabled) == 1
        assert len(disabled) == 1
        r = enabled[0]
        assert r.file_format == FileFormat.ONE_LINE
        assert r.uris == ["https://packages.example.org/ubuntu"]
        assert r.suites == ["noble"]
        assert r.components == ["main", "contrib"]
        assert r.description is None

    def test_commented_deb_line_is_disabled(self, parser, tmp_path):
        (tmp_path / "disabled.list").write_text("# deb https://example.com noble main\n")
        repos = parser.load_all()
        assert len(repos) == 1
        assert repos[0].enabled is False

    def test_pure_comment_lines_skipped(self, parser, tmp_path):
        (tmp_path / "comments.list").write_text("# This is just a comment\n")
        repos = parser.load_all()
        assert repos == []

    def test_suite_agnostic_in_list(self, parser, tmp_path):
        (tmp_path / "docker.list").write_text("deb https://download.docker.com/linux/ubuntu stable main\n")
        repos = parser.load_all()
        assert repos[0].availability == AvailabilityStatus.SUITE_AGNOSTIC

    def test_one_line_with_options_block(self, parser, tmp_path):
        (tmp_path / "opts.list").write_text(
            "deb [arch=amd64 signed-by=/etc/apt/keyrings/test.gpg] https://example.com noble main\n"
        )
        repos = parser.load_all()
        assert len(repos) == 1
        assert repos[0].uris == ["https://example.com"]
        assert repos[0].suites == ["noble"]
        assert repos[0].signed_by == "/etc/apt/keyrings/test.gpg"
        assert repos[0].architectures == ["amd64"]

    def test_one_line_signed_by_only_in_options(self, parser, tmp_path):
        """signed-by= in [options] is extracted even without arch=."""
        (tmp_path / "vpn.list").write_text(
            "deb [signed-by=/etc/apt/keyrings/openvpn.asc] https://packages.openvpn.net/openvpn3/debian noble main\n"
        )
        repos = parser.load_all()
        assert len(repos) == 1
        assert repos[0].signed_by == "/etc/apt/keyrings/openvpn.asc"
        assert repos[0].architectures == []

    def test_one_line_multi_arch_in_options(self, parser, tmp_path):
        """arch=amd64,arm64 is split into a list."""
        (tmp_path / "multi.list").write_text("deb [arch=amd64,arm64] https://example.com stable main\n")
        repos = parser.load_all()
        assert repos[0].architectures == ["amd64", "arm64"]

    def test_deb822_architectures_field_preserved(self, parser, tmp_path):
        (tmp_path / "chrome.sources").write_text(
            "Types: deb\nURIs: https://dl.google.com/linux/chrome-stable/deb/\n"
            "Suites: stable\nComponents: main\nArchitectures: amd64\n"
            "Signed-By: /usr/share/keyrings/google-chrome.gpg\n"
        )
        repos = parser.load_all()
        assert len(repos) == 1
        assert repos[0].architectures == ["amd64"]

    def test_deb822_architecture_singular_field(self, parser, tmp_path):
        """apt accepts both 'Architecture' and 'Architectures'; both should be read."""
        (tmp_path / "slack.sources").write_text(
            "Types: deb\nURIs: https://packagecloud.io/slacktechnologies/slack/debian/\n"
            "Suites: jessie\nComponents: main\nArchitecture: amd64\n"
        )
        repos = parser.load_all()
        assert repos[0].architectures == ["amd64"]

    def test_malformed_deb822_stanza_skipped(self, parser, tmp_path):
        # Stanza missing required fields
        (tmp_path / "bad.sources").write_text("Types: deb\n")
        repos = parser.load_all()
        assert repos == []

    def test_multiple_stanzas_in_one_file(self, parser, tmp_path):
        content = (
            "Types: deb\nURIs: https://one.example.com\nSuites: noble\nComponents: main\nEnabled: yes\n\n"
            "Types: deb\nURIs: https://two.example.com\nSuites: noble\nComponents: main\nEnabled: yes\n"
        )
        (tmp_path / "multi.sources").write_text(content)
        repos = parser.load_all()
        assert len(repos) == 2


class TestParserEdgeCases:
    def test_agnostic_names_fallback_to_builtin(self, monkeypatch, tmp_path):
        """When no agnostic config file exists anywhere, built-ins are returned."""
        monkeypatch.setattr(parser_module, "_USER_AGNOSTIC_CONF", tmp_path / "a.conf")
        monkeypatch.setattr(parser_module, "_SYSTEM_AGNOSTIC_CONF", tmp_path / "b.conf")
        monkeypatch.setattr(parser_module, "_DEV_AGNOSTIC_CONF", tmp_path / "c.conf")
        assert _load_agnostic_names() == _BUILTIN_AGNOSTIC

    def test_suite_agnostic_empty_suites(self):
        assert _is_suite_agnostic([], _BUILTIN_AGNOSTIC) is False

    def test_leading_comment_becomes_description(self, parser, tmp_path):
        """A bare #Name line immediately before a stanza is used as description."""
        (tmp_path / "named.sources").write_text(
            "#My Custom Repo\nTypes: deb\nURIs: https://example.com\nSuites: noble\nComponents: main\n"
        )
        repos = parser.load_all()
        assert len(repos) == 1
        assert repos[0].description == "My Custom Repo"

    def test_leading_blank_line_before_stanza(self, parser, tmp_path):
        """A blank line before the first stanza is handled without error."""
        (tmp_path / "blanklead.sources").write_text(
            "\nTypes: deb\nURIs: https://example.com\nSuites: noble\nComponents: main\n"
        )
        repos = parser.load_all()
        assert len(repos) == 1

    def test_unreadable_sources_file(self, parser, tmp_path):
        f = tmp_path / "unreadable.sources"
        f.write_text("Types: deb\nURIs: https://example.com\nSuites: noble\nComponents: main\n")
        f.chmod(0o000)
        try:
            assert parser.load_all() == []
        finally:
            f.chmod(0o644)

    def test_unreadable_list_file(self, parser, tmp_path):
        f = tmp_path / "unreadable.list"
        f.write_text("deb https://example.com noble main\n")
        f.chmod(0o000)
        try:
            assert parser.load_all() == []
        finally:
            f.chmod(0o644)

    def test_blank_lines_in_list_file_skipped(self, parser, tmp_path):
        (tmp_path / "spaced.list").write_text("\ndeb https://example.com noble main\n\n")
        repos = parser.load_all()
        assert len(repos) == 1

    def test_too_short_one_line_entry_skipped(self, parser, tmp_path):
        """A one-line entry with fewer than 3 tokens is silently skipped."""
        (tmp_path / "short.list").write_text("deb https://example.com\n")
        assert parser.load_all() == []

    def test_non_deb_type_skipped(self, parser, tmp_path):
        """Lines not starting with deb or deb-src are silently skipped."""
        (tmp_path / "rpm.list").write_text("rpm https://example.com noble main\n")
        assert parser.load_all() == []

    def test_options_block_exhausts_remaining_parts(self, parser, tmp_path):
        """A multi-token options block that consumes all remaining parts is skipped."""
        (tmp_path / "opts.list").write_text("deb [arch=amd64 signed-by=/foo/bar.gpg]\n")
        assert parser.load_all() == []

    def test_second_consecutive_comment_before_stanza_ignored(self, parser, tmp_path):
        """Only the first leading comment is used; subsequent ones before the same stanza are ignored."""
        (tmp_path / "twocomments.sources").write_text(
            "#First Comment\n#Second Comment\nTypes: deb\nURIs: https://example.com\nSuites: noble\nComponents: main\n"
        )
        repos = parser.load_all()
        assert repos[0].description == "First Comment"

    def test_bare_hash_comment_line_ignored(self, parser, tmp_path):
        """A comment line with no text after the # is not used as a description."""
        (tmp_path / "barehash.sources").write_text(
            "#\nTypes: deb\nURIs: https://example.com\nSuites: noble\nComponents: main\n"
        )
        repos = parser.load_all()
        assert repos[0].description is None


class TestOfficialUbuntuFiltering:
    """Official Ubuntu/Canonical repos must never appear in the list."""

    @pytest.mark.parametrize(
        "uri",
        [
            "http://archive.ubuntu.com/ubuntu",
            "http://security.ubuntu.com/ubuntu",
            "http://ports.ubuntu.com/ubuntu-ports",
            "https://esm.ubuntu.com/apps/ubuntu",
        ],
    )
    def test_official_deb822_uri_skipped(self, parser, tmp_path, uri):
        (tmp_path / "ubuntu.sources").write_text(
            f"Types: deb\nURIs: {uri}\nSuites: noble\nComponents: main\nEnabled: yes\n"
        )
        assert parser.load_all() == []

    @pytest.mark.parametrize(
        "uri",
        [
            "http://archive.ubuntu.com/ubuntu",
            "http://security.ubuntu.com/ubuntu",
            "http://ports.ubuntu.com/ubuntu-ports",
        ],
    )
    def test_official_one_line_uri_skipped(self, parser, tmp_path, uri):
        (tmp_path / "ubuntu.list").write_text(f"deb {uri} noble main\n")
        assert parser.load_all() == []

    def test_mixed_file_only_returns_third_party(self, parser, tmp_path):
        """A file with both official and third-party stanzas returns only the third-party one."""
        content = (
            "Types: deb\nURIs: http://archive.ubuntu.com/ubuntu\n"
            "Suites: noble\nComponents: main\nEnabled: yes\n\n"
            "Types: deb\nURIs: https://packages.example.com\n"
            "Suites: noble\nComponents: main\nEnabled: yes\n"
        )
        (tmp_path / "mixed.sources").write_text(content)
        repos = parser.load_all()
        assert len(repos) == 1
        assert repos[0].uris == ["https://packages.example.com"]

    def test_third_party_ubuntu_subdomain_not_filtered(self, parser, tmp_path):
        """A hostname that merely contains 'ubuntu' but isn't an official host is kept."""
        (tmp_path / "third.sources").write_text(
            "Types: deb\nURIs: https://ppa.launchpadcontent.net/user/ppa/ubuntu\n"
            "Suites: noble\nComponents: main\nEnabled: yes\n"
        )
        repos = parser.load_all()
        assert len(repos) == 1
