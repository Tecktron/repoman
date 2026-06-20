from __future__ import annotations

import argparse
from pathlib import Path


def _parse(argv: list[str]):
    """Run main()'s argparse logic in isolation and return (sources_dir, remaining)."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version="repoman 0.1.0")
    parser.add_argument("--sources-dir", metavar="DIR")
    args, remaining = parser.parse_known_args(argv)
    sources_dir = Path(args.sources_dir) if args.sources_dir else None
    return sources_dir, remaining


class TestArgParsing:
    def test_no_sources_dir_gives_none(self):
        sources_dir, _ = _parse([])
        assert sources_dir is None

    def test_sources_dir_parsed_as_path(self, tmp_path):
        sources_dir, _ = _parse(["--sources-dir", str(tmp_path)])
        assert sources_dir == tmp_path
        assert isinstance(sources_dir, Path)

    def test_unknown_args_passed_through(self):
        _, remaining = _parse(["--display", ":1"])
        assert "--display" in remaining
        assert ":1" in remaining

    def test_sources_dir_does_not_consume_unknown_args(self, tmp_path):
        sources_dir, remaining = _parse(["--sources-dir", str(tmp_path), "--display", ":1"])
        assert sources_dir == tmp_path
        assert "--display" in remaining
