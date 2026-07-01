"""DEB822 serialiser for Repository objects. Pure — no I/O, no GTK."""

from __future__ import annotations

from debian.deb822 import Deb822

from .models import Repository


def repo_to_deb822(repo: Repository) -> str:
    """
    Serialise a Repository to a DEB822 string.

    Called by the polkit helper (and by converter.py) — never writes directly.
    Preserves field ordering: Types, URIs, Suites, Components, Enabled,
    Signed-By (if present), X-Repolib-Name (if present).
    """
    # Leading # comment line — repolib / software-properties-gtk convention
    header = f"#{repo.description}\n" if repo.description else ""

    stanza = Deb822()
    stanza["Types"] = " ".join(repo.types)
    stanza["URIs"] = " ".join(repo.uris)
    stanza["Suites"] = " ".join(repo.suites)
    stanza["Components"] = " ".join(repo.components)
    stanza["Enabled"] = "yes" if repo.enabled else "no"
    if repo.signed_by:
        stanza["Signed-By"] = repo.signed_by
    if repo.description:
        stanza["X-Repolib-Name"] = repo.description
    return header + str(stanza) + "\n"


def enable_patch(repo: Repository, codename: str) -> dict:
    """
    Return a dict of field updates to re-enable a repo for `codename`.
    Passed as part of the JSON payload to the polkit helper.
    """
    return {"Enabled": "yes", "Suites": codename}
