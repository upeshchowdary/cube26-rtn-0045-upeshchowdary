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


# Native access violation (0xC0000005) that this Windows machine intermittently raises in child processes
# (build log P0/P3); `dev check` retries the same codes. Any other failure fails immediately.
_WIN_ACCESS_VIOLATION = (3221225477, -1073741819)


def test_entry_point_is_installed_as_returns_manager() -> None:
    for _ in range(3):
        proc = subprocess.run(
            [sys.executable, "-m", "returns_manager.cli", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        if not (sys.platform == "win32" and proc.returncode in _WIN_ACCESS_VIOLATION):
            break
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("returns-manager ")


def test_unbuilt_command_fails_and_names_its_phase(capsys: pytest.CaptureFixture[str]) -> None:
    # 'eval seal|run|report' were the P12 stubs; now that P12 is built, use a P13 stub.
    assert run(["load-test"]) == ExitCode.FAILURE
    err = capsys.readouterr().err
    assert "not built yet" in err
    assert "P13" in err


def test_unknown_command_is_a_usage_error() -> None:
    assert run(["no-such-command"]) == ExitCode.USAGE


def test_every_planned_group_has_help() -> None:
    names = {g.name for g in app.registered_groups}
    assert {
        "db",
        "reference",
        "keys",
        "controls",
        "jobs",
        "review",
        "evidence",
        "chain",
        "eval",
        "economics",
    } <= names
