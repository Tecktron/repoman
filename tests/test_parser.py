from __future__ import annotations

from pathlib import Path

import pytest

from repoman.models import AvailabilityStatus, FileFormat
from repoman.parser import Parser

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
