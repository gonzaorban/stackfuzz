"""Construcción y ejecución del comando ffuf."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List

FFUF_INSTALL_URL = "https://github.com/ffuf/ffuf"


class FfufNotFound(RuntimeError):
    """Se lanza cuando el binario de ffuf no está disponible en el PATH."""


def ensure_ffuf() -> None:
    """Lanza :class:`FfufNotFound` si ffuf no está en el PATH."""
    if shutil.which("ffuf") is None:
        raise FfufNotFound(
            "No se encontró ffuf en el PATH. Instalalo desde "
            f"{FFUF_INSTALL_URL}"
        )


def build_command(target: str, wordlist: Path, extra: List[str]) -> List[str]:
    """Arma el argv de ffuf.

    Mantiene al mínimo los flags de ffuf: solo ``-u <objetivo>/FUZZ`` y
    ``-w <wordlist>``. Los argumentos de ``extra`` se pasan tal cual, para que
    el usuario pueda añadir sus propios flags (códigos de coincidencia, hilos,
    filtros, ...).
    """
    url = target.rstrip("/") + "/FUZZ"
    return ["ffuf", "-u", url, "-w", str(wordlist), *extra]


def run(cmd: List[str], dry_run: bool) -> int:
    """Ejecuta el comando, o no hace nada en simulación, y devuelve su código.

    Mostrar el comando es tarea de quien llama (ver ``stackfuzz.output``), así
    que aquí una simulación no hace nada más que saltarse la ejecución.
    """
    if dry_run:
        return 0

    ensure_ffuf()
    result = subprocess.run(cmd)
    return result.returncode
