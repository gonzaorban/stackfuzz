"""Best-effort tech-stack fingerprinting from an initial HTTP response.

Detection relies only on cheap, side-effect-free signals: response headers,
cookie names, and the status codes of a couple of probe paths. It never parses
response bodies. Signals are unreliable in production (proxies strip
``x-powered-by`` and hide ``Server``), so ``detect`` is allowed to return an
empty set and the caller falls back to a generic wordlist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Set

import httpx

# Probe paths requested in addition to the base URL. Their status codes feed a
# few of the detection rules below.
PROBE_PATHS: List[str] = ["/admin/", "/_next/", "/api/"]

# A probe path is treated as "present" (i.e. a positive signal) when it responds
# with one of these codes. 404 / connection errors are treated as absent.
_PRESENT_CODES = frozenset({200, 301, 302, 307, 401, 403})


class Tech(str, Enum):
    """A detectable technology stack."""

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
    """Recon results for a single target.

    ``headers`` keys and ``cookies`` keys are normalised to lower case so rules
    can match without worrying about the casing a server happens to use.
    """

    status: int = 0
    headers: Dict[str, str] = field(default_factory=dict)
    cookies: Dict[str, str] = field(default_factory=dict)
    probe_paths: Dict[str, int] = field(default_factory=dict)

    def header(self, name: str) -> str:
        """Return a header value (lower-cased) or an empty string if absent."""
        return self.headers.get(name.lower(), "")

    def has_cookie(self, name: str) -> bool:
        """Return whether a cookie with the given name (case-insensitive) is set."""
        return name.lower() in self.cookies

    def probe_present(self, path: str) -> bool:
        """Return whether a probe path responded with a "present" status code."""
        return self.probe_paths.get(path, 0) in _PRESENT_CODES


def fetch_target(url: str, timeout: float = 10.0) -> Probe:
    """Fetch the base URL and probe paths, returning a :class:`Probe`.

    Network failures on the base request raise ``httpx.HTTPError`` so the caller
    can decide how to degrade. Failures on individual probe paths are swallowed
    (recorded as status ``0``) since they are only supplementary signals.
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
    """Apply signature rules to a probe, returning the detected technologies.

    Multiple technologies may match. An empty set means no signal was found and
    the caller should fall back to the generic wordlist.
    """
    techs: Set[Tech] = set()

    # --- Django -----------------------------------------------------------
    # Django's admin ships CSRF/session cookies with well-known names, and its
    # /admin/ route is almost always mounted (redirecting to a login).
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
    # NestJS runs on Express by default, so both surface as Express here.
    if "express" in _powered_by(probe):
        techs.add(Tech.EXPRESS)

    # --- Flask ------------------------------------------------------------
    # Werkzeug is Flask's WSGI layer and leaks into the Server header on the
    # dev server. The signed "session" cookie is a weaker, secondary signal.
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
