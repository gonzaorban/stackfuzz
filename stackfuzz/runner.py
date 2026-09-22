"""Build and execute the ffuf command."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List

FFUF_INSTALL_URL = "https://github.com/ffuf/ffuf"


class FfufNotFound(RuntimeError):
    """Raised when the ffuf binary is not available on PATH."""


def ensure_ffuf() -> None:
    """Raise :class:`FfufNotFound` if ffuf is not on PATH."""
    if shutil.which("ffuf") is None:
        raise FfufNotFound(
            "ffuf not found on PATH. Install it from " f"{FFUF_INSTALL_URL}"
        )


def build_command(target: str, wordlist: Path, extra: List[str]) -> List[str]:
    """Assemble the ffuf argv.

    Keeps ffuf flags minimal: only ``-u <target>/FUZZ`` and ``-w <wordlist>``.
    Any ``extra`` arguments are passed through verbatim so the user can add their
    own ffuf flags (match codes, threads, filters, ...).
    """
    url = target.rstrip("/") + "/FUZZ"
    return ["ffuf", "-u", url, "-w", str(wordlist), *extra]


def run(cmd: List[str], dry_run: bool) -> int:
    """Execute the command, or do nothing on a dry run, returning an exit code.

    Displaying the command is the caller's job (see ``stackfuzz.output``), so a
    dry run is a no-op here beyond skipping execution.
    """
    if dry_run:
        return 0

    ensure_ffuf()
    result = subprocess.run(cmd)
    return result.returncode
