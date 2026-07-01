"""Availability checker: tests repos against a target Ubuntu codename.

Runs entirely in a background thread. Never touches GTK widgets.
Uses Launchpad API for PPAs and HTTP HEAD for all other repos.
A single network failure sets a global flag that suppresses further attempts,
so one DNS outage does not cause a storm of error toasts.
"""

from __future__ import annotations

import logging

import requests

_log = logging.getLogger(__name__)

from .models import AvailabilityStatus, Repository

# Populated lazily; set to True on first network error to suppress further attempts
_network_failed = False
_network_error_message: str = ""


def reset_network_state() -> None:
    """Reset the network failure flag — useful between wizard runs."""
    global _network_failed, _network_error_message
    _network_failed = False
    _network_error_message = ""


def get_network_error() -> str:
    """Return the last network error message, or empty string if none."""
    return _network_error_message


class Checker:
    """
    Checks repo availability for a given Ubuntu codename.
    Run in a background thread — must not touch GTK widgets.

    On the first network error (timeout, DNS failure, HTTP error), the checker
    marks the global network-failed flag so the UI can surface a single alert
    and all subsequent checks return UNKNOWN immediately.
    """

    def check(self, repo: Repository, codename: str) -> AvailabilityStatus:
        """Check whether ``repo`` has packages published for ``codename``.

        Suite-agnostic repos always return SUITE_AGNOSTIC without a network call.
        If the global network-failure flag is set from a previous call, returns
        UNKNOWN immediately to avoid a cascade of timeouts.

        :param repo: The repository to check.
        :type repo: Repository
        :param codename: Ubuntu codename to check against, e.g. ``"noble"``.
        :type codename: str
        :returns: Availability status for this repo/codename pair.
        :rtype: AvailabilityStatus
        """
        global _network_failed
        if repo.availability == AvailabilityStatus.SUITE_AGNOSTIC:
            return AvailabilityStatus.SUITE_AGNOSTIC
        if _network_failed:
            return AvailabilityStatus.UNKNOWN
        if repo.is_ppa:
            return self._check_launchpad(repo, codename)
        return self._check_http(repo, codename)

    def _check_launchpad(self, repo: Repository, codename: str) -> AvailabilityStatus:
        """Query Launchpad API for published sources in the given distro series."""
        global _network_failed, _network_error_message
        try:
            from launchpadlib.launchpad import Launchpad  # type: ignore[import]

            lp = Launchpad.login_anonymously(
                "repoman",
                "production",
                version="devel",
            )
            owner = lp.people[repo.ppa_owner]
            archive = owner.getPPAByName(name=repo.ppa_name)
            series = lp.distributions["ubuntu"].getSeries(name_or_version=codename)
            sources = archive.getPublishedSources(
                distro_series=series,
                status="Published",
            )
            return AvailabilityStatus.AVAILABLE if sources.total_size > 0 else AvailabilityStatus.UNAVAILABLE
        except KeyError:
            # PPA or series not found
            return AvailabilityStatus.UNAVAILABLE
        except Exception as exc:
            _log.debug("launchpad check failed for %s/%s", repo.ppa_owner, repo.ppa_name, exc_info=True)
            _network_failed = True
            _network_error_message = str(exc)
            return AvailabilityStatus.UNKNOWN

    def _check_http(self, repo: Repository, codename: str) -> AvailabilityStatus:
        """HEAD request to {uri}/dists/{codename}/InRelease."""
        global _network_failed, _network_error_message
        try:
            uri = repo.uris[0].rstrip("/")
            url = f"{uri}/dists/{codename}/InRelease"
            response = requests.head(url, timeout=10, allow_redirects=True)
            if response.status_code == 200:
                return AvailabilityStatus.AVAILABLE
            if response.status_code == 404:
                return AvailabilityStatus.UNAVAILABLE
            # Other HTTP errors (403, 5xx, etc.) — treat as unknown
            return AvailabilityStatus.UNKNOWN
        except requests.exceptions.Timeout:
            _network_failed = True
            _network_error_message = f"Connection timed out checking {repo.uris[0]}"
            return AvailabilityStatus.UNKNOWN
        except requests.exceptions.ConnectionError:
            # DNS failure or refused connection — this specific host is unreachable,
            # not a general network outage. Treat the repo as unavailable.
            return AvailabilityStatus.UNAVAILABLE
        except requests.exceptions.RequestException as exc:
            _network_failed = True
            _network_error_message = str(exc)
            return AvailabilityStatus.UNKNOWN
