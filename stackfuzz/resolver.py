"""Map detected technologies to curated wordlists.

Each :class:`~stackfuzz.detector.Tech` points at one or more wordlist files that
ship with the package. When several technologies are detected the lists are
merged into a single temporary file with duplicates removed (first occurrence
wins, so order stays meaningful). When nothing is detected we fall back to
``generic.txt``.
"""

from __future__ import annotations

import tempfile
from importlib import resources
from pathlib import Path
from typing import Dict, Iterable, List, Set

from .detector import Tech

GENERIC_WORDLIST = "generic.txt"

# Each tech maps to the wordlist filename(s) that best fit it. Kept as a simple
# filename list so it is trivial to add more curated lists per stack later.
TECH_TO_LISTS: Dict[Tech, List[str]] = {
    Tech.DJANGO: ["django.txt"],
    Tech.NEXTJS: ["nextjs.txt"],
    Tech.EXPRESS: ["express.txt"],
    Tech.FLASK: ["flask.txt"],
    Tech.LARAVEL: ["laravel.txt"],
}


def wordlist_dir() -> Path:
    """Return the path to the bundled ``wordlists`` directory.

    Uses ``importlib.resources`` so it resolves correctly whether the package is
    run from a source checkout or an installed wheel.
    """
    return Path(str(resources.files("stackfuzz") / "wordlists"))


def resolve_wordlists(techs: Set[Tech]) -> List[Path]:
    """Return the wordlist files for the detected techs (generic if empty).

    The result preserves a stable order (techs sorted by value) so a given set
    of detections always produces the same merged list.
    """
    directory = wordlist_dir()

    if not techs:
        return [directory / GENERIC_WORDLIST]

    paths: List[Path] = []
    seen: Set[str] = set()
    for tech in sorted(techs, key=lambda t: t.value):
        for name in TECH_TO_LISTS[tech]:
            if name not in seen:
                seen.add(name)
                paths.append(directory / name)
    return paths


def _read_entries(path: Path) -> Iterable[str]:
    """Yield non-empty, non-comment lines from a wordlist file."""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            yield line


def build_merged_wordlist(paths: List[Path]) -> Path:
    """Return a single wordlist path for ffuf.

    A single input is returned untouched. Multiple inputs are merged into a new
    temporary ``.txt`` file with duplicates removed, preserving first-seen order.
    The temp file is created with ``delete=False``; the caller owns its cleanup.
    """
    if not paths:
        raise ValueError("no wordlists to merge")
    if len(paths) == 1:
        return paths[0]

    merged: List[str] = []
    seen: Set[str] = set()
    for path in paths:
        for entry in _read_entries(path):
            if entry not in seen:
                seen.add(entry)
                merged.append(entry)

    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        prefix="stackfuzz-",
        delete=False,
        encoding="utf-8",
    )
    with tmp:
        tmp.write("\n".join(merged) + "\n")
    return Path(tmp.name)
