from __future__ import annotations

import argparse


def _parse(argv: list[str]) -> list[str]:
    """Run main()'s argparse logic in isolation and return remaining (GTK) args."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version="repoman 0.1.0")
    _, remaining = parser.parse_known_args(argv)
    return remaining


class TestArgParsing:
    def test_unknown_args_passed_through(self):
        remaining = _parse(["--display", ":1"])
        assert "--display" in remaining
        assert ":1" in remaining
