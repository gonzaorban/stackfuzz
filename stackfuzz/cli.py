"""Command-line entry point for stackfuzz."""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional
from urllib.parse import urlparse

import httpx

from .detector import Probe, Tech, detect, fetch_target
from .resolver import build_merged_wordlist, resolve_wordlists
from .runner import FfufNotFound, build_command, run


def validate_target(url: str) -> str:
    """Return the target URL if it is a valid http(s) URL, else raise.

    Requires an ``http``/``https`` scheme and a host. No fuzzing happens without
    a valid target.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(
            f"invalid target URL: {url!r} (expected http(s)://host[/path])"
        )
    return url


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stackfuzz",
        description=(
            "Detect a web target's tech stack and fuzz it with ffuf using "
            "curated, stack-specific wordlists."
        ),
        epilog=(
            "Extra ffuf flags may be passed after '--', e.g. "
            "stackfuzz https://t.tld -- -mc 200,301 -t 40"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the assembled ffuf command instead of running it",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="HTTP timeout in seconds for detection (default: 10)",
    )
    parser.add_argument("target", help="target URL, e.g. https://example.com")
    return parser


def _split_ffuf_args(argv: List[str]) -> tuple[List[str], List[str]]:
    """Split argv into stackfuzz's own args and pass-through ffuf args.

    Everything after the first ``--`` is handed verbatim to ffuf. Splitting here
    (rather than relying on ``argparse.REMAINDER``) keeps stackfuzz's own options
    like ``--dry-run`` working regardless of where they appear.
    """
    if "--" in argv:
        idx = argv.index("--")
        return argv[:idx], argv[idx + 1 :]
    return argv, []


def _describe_techs(techs) -> str:
    if not techs:
        return "none detected -> using generic wordlist"
    return ", ".join(sorted(t.value for t in techs))


def main(argv: Optional[List[str]] = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    own_args, ffuf_args = _split_ffuf_args(raw)

    parser = _build_parser()
    args = parser.parse_args(own_args)

    # --- Validate target --------------------------------------------------
    try:
        target = validate_target(args.target)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # --- Recon (best-effort; degrade to empty probe on network error) -----
    try:
        probe = fetch_target(target, timeout=args.timeout)
    except httpx.HTTPError as exc:
        print(
            f"warning: could not reach target for detection ({exc}); "
            "falling back to generic wordlist",
            file=sys.stderr,
        )
        probe = Probe()

    techs = detect(probe)
    print(f"[*] detected stack: {_describe_techs(techs)}")

    # --- Resolve + merge wordlists ---------------------------------------
    wordlists = resolve_wordlists(techs)
    wordlist = build_merged_wordlist(wordlists)
    print(f"[*] wordlist: {wordlist}")

    # --- Build and run ffuf ----------------------------------------------
    cmd = build_command(target, wordlist, ffuf_args)
    try:
        return run(cmd, dry_run=args.dry_run)
    except FfufNotFound as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
