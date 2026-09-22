"""Tests del CLI: validación, separación de argumentos y flujo completo."""

import httpx
import pytest

from stackfuzz import cli
from stackfuzz.cli import _split_ffuf_args, main, validate_target


# --- validate_target ----------------------------------------------------


@pytest.mark.parametrize(
    "url",
    ["https://example.com", "http://x.tld/path", "https://host:8080"],
)
def test_validate_target_accepts_valid_urls(url):
    assert validate_target(url) == url


@pytest.mark.parametrize("url", ["notaurl", "ftp://x", "example.com", ""])
def test_validate_target_rejects_invalid_urls(url):
    with pytest.raises(ValueError):
        validate_target(url)


# --- _split_ffuf_args ---------------------------------------------------


def test_split_without_separator():
    own, extra = _split_ffuf_args(["https://x", "--dry-run"])
    assert own == ["https://x", "--dry-run"]
    assert extra == []


def test_split_with_separator():
    own, extra = _split_ffuf_args(["https://x", "--dry-run", "--", "-mc", "200"])
    assert own == ["https://x", "--dry-run"]
    assert extra == ["-mc", "200"]


# --- main(): códigos de salida y flujo ---------------------------------


def test_main_invalid_target_returns_2(capsys):
    assert main(["notaurl"]) == 2
    assert "URL objetivo inválida" in capsys.readouterr().err


def _stub_fetch(monkeypatch, probe=None, error=None):
    from stackfuzz.detector import Probe

    def fake(url, timeout=10.0):
        if error:
            raise error
        return probe if probe is not None else Probe()

    monkeypatch.setattr(cli, "fetch_target", fake)


def test_main_dry_run_prints_command_and_returns_0(monkeypatch, capsys):
    from stackfuzz.detector import Probe

    _stub_fetch(monkeypatch, probe=Probe(headers={"x-powered-by": "Next.js"}))
    code = main(["https://example.com", "--dry-run"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Stack detectado: Next.js" in out
    # La detección se justifica con la señal que la disparó.
    assert "x-powered-by: Next.js" in out
    assert "ffuf -u https://example.com/FUZZ" in out


def test_main_network_error_falls_back_to_generic(monkeypatch, capsys):
    _stub_fetch(monkeypatch, error=httpx.ConnectError("down"))
    code = main(["https://example.com", "--dry-run"])
    captured = capsys.readouterr()
    assert code == 0
    assert "No se pudo alcanzar el objetivo" in captured.err
    assert "Stack detectado: ninguno" in captured.out
    assert "generic.txt" in captured.out


def test_main_passes_extra_ffuf_args(monkeypatch, capsys):
    from stackfuzz.detector import Probe

    _stub_fetch(monkeypatch, probe=Probe())
    code = main(["https://example.com", "--dry-run", "--", "-mc", "200,301"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.strip().endswith("-mc 200,301")


def test_main_ffuf_missing_returns_1(monkeypatch, capsys):
    from stackfuzz.detector import Probe

    _stub_fetch(monkeypatch, probe=Probe())
    # ensure_ffuf resuelve shutil.which en el módulo runner: hay que
    # parchearlo allí.
    from stackfuzz import runner

    monkeypatch.setattr(runner.shutil, "which", lambda _: None)
    code = main(["https://example.com"])  # not dry-run
    assert code == 1
    assert "No se encontró ffuf en el PATH" in capsys.readouterr().err


# --- ayuda y errores de argparse, en español ---------------------------


def _capturar(capsys, argv):
    """Ejecuta main() esperando que argparse salga, y devuelve (out, err)."""
    with pytest.raises(SystemExit) as exc:
        main(argv)
    captured = capsys.readouterr()
    return captured.out, captured.err, exc.value.code


def test_help_is_fully_in_spanish(capsys):
    out, _, code = _capturar(capsys, ["--help"])
    assert code == 0
    assert out.startswith("uso:")
    assert "argumentos posicionales:" in out
    assert "opciones:" in out
    assert "muestra esta ayuda y termina" in out
    # Nada de los rótulos propios de argparse debe sobrevivir.
    for ingles in ("usage:", "positional arguments:", "options:", "show this help"):
        assert ingles not in out


def test_help_metavars_match_the_usage_line(capsys):
    out, _, _ = _capturar(capsys, ["--help"])
    assert "objetivo" in out
    assert "--timeout SEGUNDOS" in out
    # 'target' es el nombre del atributo, pero no debe mostrarse al usuario.
    assert "  target " not in out
    assert "TIMEOUT" not in out


def test_missing_argument_error_is_in_spanish(capsys):
    _, err, code = _capturar(capsys, [])
    assert code == 2
    assert "faltan argumentos obligatorios" in err
    assert "the following arguments are required" not in err


def test_unrecognised_argument_error_is_in_spanish(capsys):
    _, err, code = _capturar(capsys, ["https://x.com", "--inventado"])
    assert code == 2
    assert "argumentos no reconocidos" in err
    assert "unrecognized arguments" not in err


def test_invalid_value_error_is_in_spanish(capsys):
    _, err, code = _capturar(capsys, ["https://x.com", "--timeout", "abc"])
    assert code == 2
    assert "valor decimal inválido" in err
    assert "argumento --timeout" in err
    assert "invalid float value" not in err


def test_error_output_starts_with_translated_usage(capsys):
    _, err, _ = _capturar(capsys, [])
    assert err.startswith("uso:")


def test_version_reports_the_package_version(capsys):
    from stackfuzz import __version__

    out, _, code = _capturar(capsys, ["--version"])
    assert code == 0
    assert __version__ in out
