"""Tests para el formato de salida: colores, streams y bloques."""

import io

import pytest

from stackfuzz.output import Printer, supports_color


class _Tty(io.StringIO):
    """StringIO que se declara terminal, para probar la autodetección."""

    def isatty(self) -> bool:
        return True


# --- supports_color -----------------------------------------------------


def test_no_color_when_not_a_tty():
    assert supports_color(io.StringIO()) is False


def test_color_when_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert supports_color(_Tty()) is True


def test_no_color_env_var_wins_over_tty(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert supports_color(_Tty()) is False


# --- Printer ------------------------------------------------------------


def _printer(color=False):
    return Printer(stdout=io.StringIO(), stderr=io.StringIO(), color=color)


def test_paint_is_noop_without_color():
    assert _printer(color=False).paint("hola", "green") == "hola"


def test_paint_wraps_in_ansi_with_color():
    painted = _printer(color=True).paint("hola", "green")
    assert painted.startswith("\033[32m")
    assert painted.endswith("\033[0m")
    assert "hola" in painted


def test_paint_ignores_unknown_color():
    assert _printer(color=True).paint("hola", "chartreuse") == "hola"


def test_detected_lists_every_signal():
    out = _printer()
    out.detected("Next.js", ["cabecera A", "cookie B"])
    text = out.stdout.getvalue()
    assert "Stack detectado: Next.js" in text
    assert "cabecera A" in text
    assert "cookie B" in text


def test_not_detected_mentions_generic_fallback():
    out = _printer()
    out.not_detected()
    assert "ninguno" in out.stdout.getvalue()
    assert "genérica" in out.stdout.getvalue()


@pytest.mark.parametrize(
    "entries,expected", [(1, "1 ruta"), (18, "18 rutas"), (0, "0 rutas")]
)
def test_wordlist_pluralises_entries(entries, expected):
    out = _printer()
    out.wordlist("nextjs.txt", entries, ["nextjs.txt"])
    assert expected in out.stdout.getvalue()


def test_wordlist_lists_sources_only_when_merged():
    single = _printer()
    single.wordlist("nextjs.txt", 5, ["nextjs.txt"])
    assert "combina" not in single.stdout.getvalue()

    merged = _printer()
    merged.wordlist("listas combinadas", 9, ["django.txt", "nextjs.txt"])
    text = merged.stdout.getvalue()
    assert "combina: django.txt, nextjs.txt" in text


def test_command_distinguishes_dry_run():
    dry = _printer()
    dry.command("ffuf -u x", dry_run=True)
    assert "simulación" in dry.stdout.getvalue()

    real = _printer()
    real.command("ffuf -u x", dry_run=False)
    assert "Ejecutando ffuf" in real.stdout.getvalue()


def test_warnings_and_errors_go_to_stderr():
    out = _printer()
    out.warning("cuidado", "pista")
    out.error("falló", "otra pista")
    assert out.stdout.getvalue() == ""
    err = out.stderr.getvalue()
    assert "cuidado" in err and "pista" in err
    assert "falló" in err and "otra pista" in err


def test_hint_is_optional():
    out = _printer()
    out.error("solo el error")
    assert out.stderr.getvalue().count("\n") == 1
