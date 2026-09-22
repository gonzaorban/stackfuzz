"""Correspondencia entre las tecnologías detectadas y las wordlists curadas.

Cada :class:`~stackfuzz.detector.Tech` apunta a uno o más ficheros de wordlist
incluidos en el paquete. Cuando se detectan varias tecnologías, las listas se
fusionan en un único fichero temporal sin duplicados (gana la primera aparición,
de modo que el orden sigue siendo significativo). Si no se detecta nada, se
recurre a ``generic.txt``.
"""

from __future__ import annotations

import tempfile
from importlib import resources
from pathlib import Path
from typing import Dict, Iterable, List, Set

from .detector import Tech

GENERIC_WORDLIST = "generic.txt"

# Cada tecnología apunta al nombre (o nombres) de wordlist que mejor le encaja.
# Se mantiene como una simple lista de nombres para que añadir más listas
# curadas por stack sea trivial.
TECH_TO_LISTS: Dict[Tech, List[str]] = {
    Tech.DJANGO: ["django.txt"],
    Tech.NEXTJS: ["nextjs.txt"],
    Tech.EXPRESS: ["express.txt"],
    Tech.FLASK: ["flask.txt"],
    Tech.LARAVEL: ["laravel.txt"],
}


def wordlist_dir() -> Path:
    """Devuelve la ruta al directorio ``wordlists`` incluido en el paquete.

    Usa ``importlib.resources`` para que se resuelva bien tanto si el paquete se
    ejecuta desde el código fuente como desde un wheel instalado.
    """
    return Path(str(resources.files("stackfuzz") / "wordlists"))


def resolve_wordlists(techs: Set[Tech]) -> List[Path]:
    """Devuelve las wordlists de las tecnologías detectadas (genérica si no hay).

    El resultado mantiene un orden estable (tecnologías ordenadas por su valor),
    de modo que un mismo conjunto de detecciones produce siempre la misma lista
    fusionada.
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


def count_entries(path: Path) -> int:
    """Devuelve cuántas rutas efectivas contiene una wordlist.

    Ignora líneas en blanco y comentarios, de modo que el número coincida con lo
    que ffuf realmente va a probar.
    """
    try:
        return sum(1 for _ in _read_entries(path))
    except OSError:
        return 0


def _read_entries(path: Path) -> Iterable[str]:
    """Genera las líneas de una wordlist que no están vacías ni son comentarios."""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            yield line


def build_merged_wordlist(paths: List[Path]) -> Path:
    """Devuelve una única ruta de wordlist para pasarle a ffuf.

    Si solo hay una entrada, se devuelve sin tocar. Varias entradas se fusionan
    en un fichero ``.txt`` temporal nuevo, sin duplicados y conservando el orden
    de primera aparición. El temporal se crea con ``delete=False``: su limpieza
    queda en manos de quien llama.
    """
    if not paths:
        raise ValueError("no hay wordlists que fusionar")
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
