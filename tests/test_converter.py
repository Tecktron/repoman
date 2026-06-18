from __future__ import annotations

from pathlib import Path

import pytest

from repoman.converter import convert_to_deb822
from repoman.models import FileFormat, Repository

FIXTURES = Path(__file__).parent / "fixtures"


def _make_one_line_repo(tmp_path: Path) -> Repository:
    src = FIXTURES / "sample_legacy.list"
    dest = tmp_path / "sample_legacy.list"
    dest.write_text(src.read_text())
    from repoman.parser import Parser

    parser = Parser(sources_dir=tmp_path)
    repos = parser.load_all()
    assert repos, "Fixture produced no repos"
    return repos[0]


class TestConverter:
    def test_returns_sources_path(self, tmp_path):
        repo = _make_one_line_repo(tmp_path)
        new_path, _ = convert_to_deb822(repo)
        assert new_path.suffix == ".sources"
        assert new_path.stem == "sample_legacy"

    def test_returns_valid_deb822_content(self, tmp_path):
        repo = _make_one_line_repo(tmp_path)
        _, content = convert_to_deb822(repo)
        assert "Types:" in content
        assert "URIs:" in content
        assert "Suites:" in content

    def test_updates_repo_in_memory(self, tmp_path):
        repo = _make_one_line_repo(tmp_path)
        original_path = repo.source_file
        convert_to_deb822(repo)
        assert repo.file_format == FileFormat.DEB822
        assert repo.source_file != original_path
        assert repo.source_file.suffix == ".sources"

    def test_preserves_uri_and_suite(self, tmp_path):
        repo = _make_one_line_repo(tmp_path)
        original_uri = repo.uris[0]
        original_suite = repo.suites[0]
        _, content = convert_to_deb822(repo)
        assert original_uri in content
        assert original_suite in content

    def test_raises_on_deb822_input(self, tmp_path):
        from repoman.parser import Parser

        (tmp_path / "test.sources").write_text(
            "Types: deb\nURIs: https://example.com\nSuites: noble\nComponents: main\nEnabled: yes\n"
        )
        repos = Parser(sources_dir=tmp_path).load_all()
        with pytest.raises(ValueError, match="ONE_LINE"):
            convert_to_deb822(repos[0])
