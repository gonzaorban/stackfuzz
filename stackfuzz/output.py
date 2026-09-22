"""Formato de la salida de consola: colores, símbolos y bloques de texto.

Centraliza aquí todo lo que se imprime para que ``cli`` se lea como el flujo del
programa y no como una sucesión de ``print``. Los colores se desactivan solos
cuando la salida no es una terminal (redirección a archivo o pipe), cuando la
variable ``NO_COLOR`` está definida, o con ``--no-color``.
"""

from __future__ import annotations

import os
import sys
from typing import IO, Optional

# Códigos ANSI. Se usan solo a través de :func:`Printer.paint`, que los omite
# cuando el color está desactivado.
_RESET = "\033[0m"
_COLORS = {
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "cyan": "\033[36m",
    "dim": "\033[2m",
    "bold": "\033[1m",
}


def supports_color(stream: IO[str]) -> bool:
    """Indica si conviene emitir códigos ANSI en ``stream``.

    Respeta la convención ``NO_COLOR`` (https://no-color.org) y exige que la
    salida sea una terminal interactiva.
    """
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(stream, "isatty") and stream.isatty()


class Printer:
    """Escribe los mensajes del programa con un formato uniforme.

    ``stdout`` recibe el resultado del análisis y el comando ffuf; ``stderr``
    recibe advertencias y errores, de modo que ``stackfuzz ... > salida.txt``
    guarde solo lo útil.
    """

    def __init__(
        self,
        stdout: Optional[IO[str]] = None,
        stderr: Optional[IO[str]] = None,
        color: Optional[bool] = None,
    ) -> None:
        self.stdout = stdout if stdout is not None else sys.stdout
        self.stderr = stderr if stderr is not None else sys.stderr
        self.color = supports_color(self.stdout) if color is None else color

    # --- primitivas ------------------------------------------------------

    def paint(self, text: str, color: str) -> str:
        """Devuelve ``text`` coloreado, o sin cambios si el color está apagado."""
        if not self.color or color not in _COLORS:
            return text
        return f"{_COLORS[color]}{text}{_RESET}"

    def _line(self, text: str = "", stream: Optional[IO[str]] = None) -> None:
        target = stream if stream is not None else self.stdout
        # stderr suele estar sin buffer y stdout no; vaciar stdout antes de
        # escribir mantiene el orden de los mensajes cuando se redirige.
        if target is self.stderr:
            self._flush(self.stdout)
        print(text, file=target)
        self._flush(target)

    @staticmethod
    def _flush(stream: IO[str]) -> None:
        try:
            stream.flush()
        except (ValueError, OSError):
            pass

    # --- bloques ---------------------------------------------------------

    def header(self, version: str, target: str) -> None:
        """Cabecera con la versión y el objetivo analizado."""
        self._line()
        self._line(f"  {self.paint('stackfuzz', 'bold')} {self.paint('v' + version, 'dim')}")
        self._line()
        self._line(f"  {self.paint('Objetivo', 'dim')}    {target}")

    def response(self, status: int, elapsed: float) -> None:
        """Resumen de la petición de reconocimiento."""
        color = "green" if 200 <= status < 400 else "yellow"
        detail = f"{self.paint(str(status), color)} en {elapsed:.2f}s"
        self._line(f"  {self.paint('Respuesta', 'dim')}   {detail}")
        self._line()

    def detected(self, label: str, signals: list) -> None:
        """Stack detectado, con las señales que lo dispararon."""
        self._line(f"{self.paint('[✓]', 'green')} Stack detectado: {self.paint(label, 'bold')}")
        for signal in signals:
            self._line(self.paint(f"    └─ señal: {signal}", "dim"))

    def not_detected(self) -> None:
        """Ningún stack reconocido: se usará la lista genérica."""
        self._line(f"{self.paint('[~]', 'yellow')} Stack detectado: {self.paint('ninguno', 'bold')}")
        self._line(
            self.paint(
                "    └─ sin señales concluyentes; se usa la wordlist genérica", "dim"
            )
        )

    def wordlist(self, name: str, entries: int, sources: list) -> None:
        """Wordlist elegida, con su tamaño y las listas que la componen."""
        plural = "ruta" if entries == 1 else "rutas"
        self._line(
            f"{self.paint('[»]', 'cyan')} Wordlist: {self.paint(name, 'bold')} "
            f"{self.paint(f'— {entries} {plural}', 'dim')}"
        )
        if len(sources) > 1:
            combinadas = ", ".join(sources)
            self._line(self.paint(f"    └─ combina: {combinadas}", "dim"))

    def command(self, rendered: str, dry_run: bool) -> None:
        """Comando ffuf, destacado del resto del log."""
        title = "Comando ffuf (simulación, no se ejecuta):" if dry_run else "Ejecutando ffuf:"
        self._line()
        self._line(f"{self.paint('[»]', 'cyan')} {title}")
        self._line()
        self._line(f"    {rendered}")
        self._line()

    def warning(self, message: str, hint: str = "") -> None:
        """Advertencia recuperable: el programa continúa."""
        self._line(f"{self.paint('[!]', 'yellow')} {message}", stream=self.stderr)
        if hint:
            self._line(self.paint(f"    └─ {hint}", "dim"), stream=self.stderr)

    def error(self, message: str, hint: str = "") -> None:
        """Error que aborta la ejecución."""
        self._line(f"{self.paint('[x]', 'red')} {message}", stream=self.stderr)
        if hint:
            self._line(self.paint(f"    └─ {hint}", "dim"), stream=self.stderr)
