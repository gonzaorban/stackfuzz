"""Punto de entrada de línea de comandos de stackfuzz."""

from __future__ import annotations

import argparse
import shlex
import sys
import time
from typing import List, Optional
from urllib.parse import urlparse

import httpx

from . import __version__
from .detector import Probe, Tech, detect, explain, fetch_target, label
from .output import Printer
from .resolver import build_merged_wordlist, count_entries, resolve_wordlists
from .runner import FfufNotFound, build_command, run


def validate_target(url: str) -> str:
    """Devuelve la URL objetivo si es una URL http(s) válida; si no, lanza error.

    Exige un esquema ``http``/``https`` y un host. Sin un objetivo válido no se
    ejecuta ningún fuzzing.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(
            f"URL objetivo inválida: {url!r} (se espera http(s)://host[/ruta])"
        )
    return url


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stackfuzz",
        description=(
            "Detecta el stack tecnológico de un objetivo web y lo fuzzea con "
            "ffuf usando wordlists curadas para ese stack."
        ),
        epilog=(
            "Se pueden pasar flags adicionales a ffuf después de '--', p. ej. "
            "stackfuzz https://t.tld -- -mc 200,301 -t 40"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="muestra el comando ffuf en lugar de ejecutarlo",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="tiempo límite HTTP en segundos para la detección (por defecto: 10)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="desactiva los colores de la salida",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"stackfuzz {__version__}",
        help="muestra la versión y termina",
    )
    parser.add_argument("target", help="URL objetivo, p. ej. https://example.com")
    return parser


def _split_ffuf_args(argv: List[str]) -> tuple[List[str], List[str]]:
    """Separa argv entre los argumentos propios y los que se pasan a ffuf.

    Todo lo que va después del primer ``--`` se entrega tal cual a ffuf. Hacer
    la división aquí (en vez de depender de ``argparse.REMAINDER``) mantiene
    operativas las opciones propias como ``--dry-run`` aparezcan donde
    aparezcan.
    """
    if "--" in argv:
        idx = argv.index("--")
        return argv[:idx], argv[idx + 1 :]
    return argv, []


def _enable_utf8_console() -> None:
    """Reconfigura la consola a UTF-8 cuando es posible.

    En Windows la página de códigos por defecto no representa los símbolos que
    usa la salida. Si la reconfiguración falla, ``Printer`` seguirá escribiendo
    y el intérprete sustituirá los caracteres no representables.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _describe_techs(techs) -> str:
    """Resumen de una línea de las tecnologías detectadas."""
    if not techs:
        return "ninguna detectada -> se usa la wordlist genérica"
    return ", ".join(label(t) for t in sorted(techs, key=lambda t: t.value))


def main(argv: Optional[List[str]] = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    own_args, ffuf_args = _split_ffuf_args(raw)

    _enable_utf8_console()

    parser = _build_parser()
    args = parser.parse_args(own_args)

    out = Printer(color=False if args.no_color else None)

    # --- Validación del objetivo -----------------------------------------
    try:
        target = validate_target(args.target)
    except ValueError as exc:
        out.error(
            str(exc),
            "Se espera una URL completa, p. ej. https://example.com",
        )
        return 2

    out.header(__version__, target)

    # --- Reconocimiento (si falla, se degrada a un probe vacío) -----------
    started = time.monotonic()
    try:
        probe = fetch_target(target, timeout=args.timeout)
        out.response(probe.status, time.monotonic() - started)
    except httpx.HTTPError as exc:
        out.warning(
            f"No se pudo alcanzar el objetivo para la detección: {exc}",
            "Se continúa con la wordlist genérica",
        )
        probe = Probe()

    techs = detect(probe)
    if techs:
        reasons = explain(probe)
        signals = [
            señal
            for tech in sorted(techs, key=lambda t: t.value)
            for señal in reasons.get(tech, [])
        ]
        out.detected(_describe_techs(techs), signals)
    else:
        out.not_detected()

    # --- Resolución y fusión de wordlists --------------------------------
    wordlists = resolve_wordlists(techs)
    wordlist = build_merged_wordlist(wordlists)
    out.wordlist(
        wordlist.name if len(wordlists) == 1 else "listas combinadas",
        count_entries(wordlist),
        [p.name for p in wordlists],
    )

    # --- Construcción y ejecución de ffuf --------------------------------
    cmd = build_command(target, wordlist, ffuf_args)
    out.command(shlex.join(cmd), dry_run=args.dry_run)
    try:
        return run(cmd, dry_run=args.dry_run)
    except FfufNotFound as exc:
        out.error(
            str(exc),
            "Hace falta solo para fuzzear: con --dry-run funciona igual",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
