"""P0: the CLI skeleton runs, and exit codes follow §20."""

from __future__ import annotations

import subprocess
import sys

import pytest

from returns_manager.cli.main import app, run
from returns_manager.errors import ExitCode


def test_help_exits_zero_and_lists_command_groups(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["--help"]) == ExitCode.OK
    out = capsys.readouterr().out
    for group in ("db", "keys", "controls", "inspect", "chain", "eval", "dev", "quota"):
        assert group in out


def test_entry_point_is_installed_as_returns_manager() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "returns_manager.cli", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("returns-manager ")


def test_unbuilt_command_fails_and_names_its_phase(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["inspect", "--unit", "UNIT-0001"]) == ExitCode.FAILURE
    err = capsys.readouterr().err
    assert "not built yet" in err
    assert "P5" in err


def test_unknown_command_is_a_usage_error() -> None:
    assert run(["no-such-command"]) == ExitCode.USAGE


def test_every_planned_group_has_help() -> None:
    names = {g.name for g in app.registered_groups}
    assert {"db", "reference", "keys", "controls", "jobs", "review", "evidence", "chain", "eval"} <= names
