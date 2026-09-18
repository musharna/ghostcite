"""Version identity across every place ghostcite records it.

Ported from data-aggregator-mcp, the only repo in this account that had such a
test. It earned its keep immediately, catching two incomplete version bumps during
the v0.45.1 release; the repos without it stayed green while carrying a stale
``__version__``.

ghostcite has already been bitten by the citation half of this: CITATION.cff
claimed 0.4.0 for a month while the project shipped 0.5.0, because nothing
compared them.
"""

from __future__ import annotations

from pathlib import Path

# tomllib is stdlib only from 3.11; ghostcite supports >=3.9 and CI runs 3.9.
try:  # pragma: no cover - trivial import shim
    import tomllib
except ModuleNotFoundError:  # Python 3.9 / 3.10
    import tomli as tomllib

import ghostcite

_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT = tomllib.loads((_ROOT / "pyproject.toml").read_text())


def _cff_version() -> str:
    cff = (_ROOT / "CITATION.cff").read_text()
    line = next(ln for ln in cff.splitlines() if ln.startswith("version:"))
    return line.split(":", 1)[1].strip().strip("\"'")


def test_module_version_matches_pyproject() -> None:
    assert ghostcite.__version__ == _PYPROJECT["project"]["version"], (
        f"__version__ {ghostcite.__version__!r} != pyproject version "
        f"{_PYPROJECT['project']['version']!r}"
    )


def test_citation_cff_version_matches_pyproject() -> None:
    """CITATION.cff feeds GitHub's cite panel and the Zenodo DOI record.

    Stale citation metadata is worse than none: it is machine-readable, and a wrong
    version propagates into other people's bibliographies where nobody re-checks it
    against the tag.
    """
    assert _cff_version() == _PYPROJECT["project"]["version"], (
        f"CITATION.cff version {_cff_version()!r} != pyproject version "
        f"{_PYPROJECT['project']['version']!r}"
    )


def _action_pin() -> str:
    import re

    pins = re.findall(
        r'pip install "ghostcite(?:\[pdf\])?==([^"]+)"', (_ROOT / "action.yml").read_text()
    )
    assert len(pins) == 1, f"expected exactly one ghostcite pin in action.yml, found {pins}"
    return pins[0]


def test_action_installs_the_released_version() -> None:
    """`uses: musharna/ghostcite@v1` installs whatever action.yml pins.

    release.yml force-moves the `v1` tag to every release commit, so the pin in
    that commit is what Action users run. It sat at 0.4.0 through 0.5.0-0.5.3:
    the tag advanced four times and every consumer kept a four-release-old tool.
    """
    assert _action_pin() == _PYPROJECT["project"]["version"], (
        f"action.yml pins ghostcite=={_action_pin()} but this commit releases "
        f"{_PYPROJECT['project']['version']}"
    )
