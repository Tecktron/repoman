from __future__ import annotations

from pathlib import Path

from debian.deb822 import Deb822

from repoman.models import FileFormat, Repository
from repoman.writer import enable_patch, repo_to_deb822

FIXTURES = Path(__file__).parent / "fixtures"


def _make_repo(**overrides) -> Repository:
    defaults = {
        "source_file": Path("/etc/apt/sources.list.d/test.sources"),
        "file_format": FileFormat.DEB822,
        "types": ["deb"],
        "uris": ["https://packages.example.com/ubuntu"],
        "suites": ["noble"],
        "components": ["main"],
        "enabled": True,
        "description": "Test repo",
        "signed_by": "/usr/share/keyrings/test.gpg",
    }
    defaults.update(overrides)
    return Repository(**defaults)


class TestRepotoDeb822:
    def test_round_trips_basic_fields(self):
        repo = _make_repo()
        content = repo_to_deb822(repo)
        parsed = Deb822(content)
        assert parsed["Types"] == "deb"
        assert parsed["URIs"] == "https://packages.example.com/ubuntu"
        assert parsed["Suites"] == "noble"
        assert parsed["Components"] == "main"
        assert parsed["Enabled"] == "yes"

    def test_disabled_repo(self):
        repo = _make_repo(enabled=False)
        content = repo_to_deb822(repo)
        parsed = Deb822(content)
        assert parsed["Enabled"] == "no"

    def test_description_included_when_set(self):
        repo = _make_repo(description="My repo description")
        content = repo_to_deb822(repo)
        assert "X-Repolib-Name: My repo description" in content

    def test_description_absent_when_none(self):
        repo = _make_repo(description=None)
        content = repo_to_deb822(repo)
        assert "X-Repolib-Name" not in content
        assert "Description" not in content

    def test_signed_by_absent_when_none(self):
        repo = _make_repo(signed_by=None)
        content = repo_to_deb822(repo)
        assert "Signed-By" not in content

    def test_multiple_types(self):
        repo = _make_repo(types=["deb", "deb-src"])
        content = repo_to_deb822(repo)
        parsed = Deb822(content)
        assert parsed["Types"] == "deb deb-src"

    def test_multiple_components(self):
        repo = _make_repo(components=["main", "contrib", "non-free"])
        content = repo_to_deb822(repo)
        parsed = Deb822(content)
        assert parsed["Components"] == "main contrib non-free"

    def test_output_is_valid_deb822(self):
        repo = _make_repo()
        content = repo_to_deb822(repo)
        # Should parse without error and have all required keys
        parsed = Deb822(content)
        assert "Types" in parsed
        assert "URIs" in parsed
        assert "Suites" in parsed


class TestEnablePatch:
    def test_returns_correct_fields(self):
        repo = _make_repo(enabled=False, suites=["jammy"])
        patch = enable_patch(repo, "noble")
        assert patch["Enabled"] == "yes"
        assert patch["Suites"] == "noble"

    def test_does_not_mutate_repo(self):
        repo = _make_repo(enabled=False, suites=["jammy"])
        enable_patch(repo, "noble")
        assert repo.enabled is False
        assert repo.suites == ["jammy"]
