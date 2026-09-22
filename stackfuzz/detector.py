"""Identificación aproximada del stack a partir de una respuesta HTTP inicial.

La detección usa solo señales baratas y sin efectos secundarios: cabeceras de
respuesta, nombres de cookies y los códigos de estado de un par de rutas de
sondeo. Nunca analiza el cuerpo de la respuesta. Las señales son poco fiables en
producción (los proxies eliminan ``x-powered-by`` y ocultan ``Server``), así que
``detect`` puede devolver un conjunto vacío y quien la llama recurre a una
wordlist genérica.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Set

import httpx

# Rutas de sondeo que se piden además de la URL base. Sus códigos de estado
# alimentan algunas de las reglas de detección de más abajo.
PROBE_PATHS: List[str] = ["/admin/", "/_next/", "/api/"]

# Una ruta de sondeo se considera "presente" (es decir, señal positiva) cuando
# responde con alguno de estos códigos. Un 404 o un error de conexión se tratan
# como ausencia.
_PRESENT_CODES = frozenset({200, 301, 302, 307, 401, 403})


class Tech(str, Enum):
    """Una tecnología que el detector es capaz de reconocer."""

    DJANGO = "django"
    NEXTJS = "nextjs"
    EXPRESS = "express"
    FLASK = "flask"
    LARAVEL = "laravel"


# Nombre presentable de cada tecnología, para los mensajes del CLI.
TECH_LABELS: Dict["Tech", str] = {
    Tech.DJANGO: "Django",
    Tech.NEXTJS: "Next.js",
    Tech.EXPRESS: "NestJS/Express",
    Tech.FLASK: "Flask",
    Tech.LARAVEL: "Laravel",
}


def label(tech: "Tech") -> str:
    """Devuelve el nombre presentable de una tecnología."""
    return TECH_LABELS.get(tech, tech.value)


@dataclass
class Probe:
    """Resultado del reconocimiento de un objetivo.

    Las claves de ``headers`` y ``cookies`` se normalizan a minúsculas para que
    las reglas puedan coincidir sin preocuparse por las mayúsculas que use cada
    servidor.
    """

    status: int = 0
    headers: Dict[str, str] = field(default_factory=dict)
    cookies: Dict[str, str] = field(default_factory=dict)
    probe_paths: Dict[str, int] = field(default_factory=dict)

    def header(self, name: str) -> str:
        """Devuelve el valor de una cabecera, o cadena vacía si no está."""
        return self.headers.get(name.lower(), "")

    def has_cookie(self, name: str) -> bool:
        """Indica si existe una cookie con ese nombre (sin distinguir mayúsculas)."""
        return name.lower() in self.cookies

    def probe_present(self, path: str) -> bool:
        """Indica si una ruta de sondeo respondió con un código de "presente"."""
        return self.probe_paths.get(path, 0) in _PRESENT_CODES


def fetch_target(url: str, timeout: float = 10.0) -> Probe:
    """Pide la URL base y las rutas de sondeo, devolviendo un :class:`Probe`.

    Los fallos de red en la petición base lanzan ``httpx.HTTPError`` para que
    quien la llama decida cómo degradar. Los fallos en rutas de sondeo concretas
    se ignoran (se registran con estado ``0``), ya que son señales secundarias.
    """
    base = url.rstrip("/")
    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        response = client.get(base)

        headers = {k.lower(): v for k, v in response.headers.items()}
        cookies = {k.lower(): v for k, v in response.cookies.items()}

        probe_paths: Dict[str, int] = {}
        for path in PROBE_PATHS:
            try:
                probe = client.get(base + path)
                probe_paths[path] = probe.status_code
            except httpx.HTTPError:
                probe_paths[path] = 0

    return Probe(
        status=response.status_code,
        headers=headers,
        cookies=cookies,
        probe_paths=probe_paths,
    )


def _server(probe: Probe) -> str:
    return probe.header("server").lower()


def _powered_by(probe: Probe) -> str:
    return probe.header("x-powered-by").lower()


def detect(probe: Probe) -> Set[Tech]:
    """Aplica las reglas de firma a un probe y devuelve las tecnologías halladas.

    Pueden coincidir varias tecnologías. Un conjunto vacío significa que no se
    encontró ninguna señal y que conviene recurrir a la wordlist genérica.
    """
    techs: Set[Tech] = set()

    # --- Django -----------------------------------------------------------
    # El admin de Django emite cookies de CSRF/sesión con nombres conocidos, y
    # su ruta /admin/ casi siempre está montada (redirige a un login).
    if probe.has_cookie("csrftoken") or probe.has_cookie("sessionid"):
        techs.add(Tech.DJANGO)
    if probe.probe_present("/admin/") and "django" in _powered_by(probe):
        techs.add(Tech.DJANGO)

    # --- Next.js ----------------------------------------------------------
    if "next.js" in _powered_by(probe):
        techs.add(Tech.NEXTJS)
    if any(h.startswith("x-nextjs-") for h in probe.headers):
        techs.add(Tech.NEXTJS)
    if probe.probe_present("/_next/"):
        techs.add(Tech.NEXTJS)

    # --- Express / NestJS -------------------------------------------------
    # NestJS corre sobre Express por defecto, así que ambos aparecen como
    # Express aquí.
    if "express" in _powered_by(probe):
        techs.add(Tech.EXPRESS)

    # --- Flask ------------------------------------------------------------
    # Werkzeug es la capa WSGI de Flask y se filtra en la cabecera Server del
    # servidor de desarrollo. La cookie firmada "session" es una señal más
    # débil, secundaria.
    if "werkzeug" in _server(probe):
        techs.add(Tech.FLASK)
    if probe.has_cookie("session") and not (
        probe.has_cookie("csrftoken") or probe.has_cookie("sessionid")
    ):
        techs.add(Tech.FLASK)

    # --- Laravel ----------------------------------------------------------
    if probe.has_cookie("laravel_session") or probe.has_cookie("xsrf-token"):
        techs.add(Tech.LARAVEL)

    return techs


def explain(probe: Probe) -> Dict[Tech, List[str]]:
    """Describe, por tecnología, qué señales de :func:`detect` se activaron.

    Sirve para que el CLI pueda justificar cada detección. Refleja las mismas
    reglas que :func:`detect`, de modo que sus claves siempre coinciden con el
    conjunto que aquella devuelve.
    """
    reasons: Dict[Tech, List[str]] = {}

    def add(tech: Tech, reason: str) -> None:
        reasons.setdefault(tech, []).append(reason)

    # --- Django -----------------------------------------------------------
    for cookie in ("csrftoken", "sessionid"):
        if probe.has_cookie(cookie):
            add(Tech.DJANGO, f"cookie «{cookie}»")
    if probe.probe_present("/admin/") and "django" in _powered_by(probe):
        add(Tech.DJANGO, "cabecera «x-powered-by: Django» y /admin/ accesible")

    # --- Next.js ----------------------------------------------------------
    if "next.js" in _powered_by(probe):
        add(Tech.NEXTJS, "cabecera «x-powered-by: Next.js»")
    for header in sorted(h for h in probe.headers if h.startswith("x-nextjs-")):
        add(Tech.NEXTJS, f"cabecera «{header}»")
    if probe.probe_present("/_next/"):
        status = probe.probe_paths.get("/_next/", 0)
        add(Tech.NEXTJS, f"ruta /_next/ responde {status}")

    # --- Express / NestJS -------------------------------------------------
    if "express" in _powered_by(probe):
        add(Tech.EXPRESS, "cabecera «x-powered-by: Express»")

    # --- Flask ------------------------------------------------------------
    if "werkzeug" in _server(probe):
        add(Tech.FLASK, f"cabecera «server: {probe.header('server')}»")
    if probe.has_cookie("session") and not (
        probe.has_cookie("csrftoken") or probe.has_cookie("sessionid")
    ):
        add(Tech.FLASK, "cookie «session» (sin cookies de Django)")

    # --- Laravel ----------------------------------------------------------
    for cookie in ("laravel_session", "xsrf-token"):
        if probe.has_cookie(cookie):
            add(Tech.LARAVEL, f"cookie «{cookie}»")

    return reasons
