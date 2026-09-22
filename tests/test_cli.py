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
