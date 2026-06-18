from __future__ import annotations

import subprocess

from .models import Repository
from .paths import LSB_RELEASE


def get_current_codename() -> str:
    """Return the running Ubuntu codename, e.g. 'noble'."""
    r = subprocess.run([LSB_RELEASE, "-cs"], capture_output=True, text=True)
    return r.stdout.strip()


def repos_needing_attention(repos: list[Repository]) -> list[Repository]:
    """
    Return repos that need review. Catches two cases:
      1. Disabled repos (Enabled: no).
      2. Enabled repos pointing at a stale codename — these appear healthy
         but silently 404 on every `apt update`. This is the case most
         tools miss.

    Excludes suite-agnostic repos ('stable', 'main', anything non-alphabetic
    like 'focal-security') — those don't need a codename update.
    """
    current = get_current_codename()
    flagged = []
    for repo in repos:
        if not repo.enabled:
            flagged.append(repo)
            continue
        for suite in repo.suites:
            is_release_codename = suite.isalpha() and suite.islower()
            if is_release_codename and suite != current:
                flagged.append(repo)
                break
    return flagged
