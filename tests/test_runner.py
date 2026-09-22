"""Tests for building, checking and dispatching the ffuf command."""

from pathlib import Path

import pytest

from stackfuzz import runner
from stackfuzz.runner import (
    FfufNotFound,
    build_command,
    ensure_ffuf,
    run,
)


def test_build_command_basic():
    wl = Path("wordlist.txt")
    cmd = build_command("https://example.com", wl, [])
    # -w carries the OS-native string form of the path, so compare against that.
    assert cmd == [
        "ffuf",
        "-u",
        "https://example.com/FUZZ",
        "-w",
        str(wl),
    ]


def test_build_command_strips_trailing_slash():
    cmd = build_command("https://example.com/", Path("wl.txt"), [])
    assert cmd[2] == "https://example.com/FUZZ"


def test_build_command_appends_extra_args():
    cmd = build_command("https://x", Path("wl.txt"), ["-mc", "200", "-t", "40"])
    assert cmd[-4:] == ["-mc", "200", "-t", "40"]


def test_dry_run_does_not_execute(capsys, monkeypatch):
    # If run() tried to execute, this would blow up; dry-run must not reach it.
    monkeypatch.setattr(
        runner.subprocess, "run", lambda *a, **k: pytest.fail("should not run")
    )
    code = run(["ffuf", "-u", "https://x/FUZZ", "-w", "wl.txt"], dry_run=True)
    assert code == 0
    # Mostrar el comando es tarea del CLI, no del runner.
    assert capsys.readouterr().out == ""


def test_ensure_ffuf_raises_when_missing(monkeypatch):
    monkeypatch.setattr(runner.shutil, "which", lambda _: None)
    with pytest.raises(FfufNotFound):
        ensure_ffuf()


def test_ensure_ffuf_passes_when_present(monkeypatch):
    monkeypatch.setattr(runner.shutil, "which", lambda _: "/usr/bin/ffuf")
    ensure_ffuf()  # should not raise


def test_run_executes_when_ffuf_present(monkeypatch):
    monkeypatch.setattr(runner.shutil, "which", lambda _: "/usr/bin/ffuf")

    class Result:
        returncode = 7

    called = {}

    def fake_run(cmd):
        called["cmd"] = cmd
        return Result()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    code = run(["ffuf", "-u", "https://x/FUZZ", "-w", "wl.txt"], dry_run=False)
    assert code == 7
    assert called["cmd"][0] == "ffuf"


def test_run_raises_when_ffuf_missing_and_not_dry_run(monkeypatch):
    monkeypatch.setattr(runner.shutil, "which", lambda _: None)
    with pytest.raises(FfufNotFound):
        run(["ffuf"], dry_run=False)
