"""`returns-manager dev check`: ruff + mypy + pytest (non-live) + reference validate + boundary check."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import typer

from returns_manager.config import AGENT_ROOT, REPO_ROOT
from returns_manager.errors import ExitCode

app = typer.Typer(no_args_is_help=True)


@dataclass(frozen=True)
class Step:
    name: str
    argv: list[str]
    cwd: Path
    skip_reason: str | None = None


def _steps() -> list[Step]:
    py = sys.executable
    return [
        Step("ruff lint", [py, "-m", "ruff", "check", "."], AGENT_ROOT),
        Step("ruff format", [py, "-m", "ruff", "format", "--check", "."], AGENT_ROOT),
        Step("mypy", [py, "-m", "mypy"], AGENT_ROOT),
        Step("pytest (non-live)", [py, "-m", "pytest", "-q"], AGENT_ROOT),
        Step("reference validate", [py, "-m", "returns_manager", "reference", "validate"], AGENT_ROOT),
        Step("boundary check", [py, str(REPO_ROOT / "scripts" / "check_boundary.py")], REPO_ROOT),
    ]


@app.command("check")
def check() -> None:
    """Run every local quality gate; exit 1 if any fails."""
    failed: list[str] = []
    for step in _steps():
        if step.skip_reason:
            typer.echo(f"-- {step.name}: SKIPPED ({step.skip_reason})")
            continue
        typer.echo(f"-- {step.name}: running")
        proc = subprocess.run(step.argv, cwd=step.cwd, check=False)  # noqa: S603 (fixed argv)
        status = "ok" if proc.returncode == 0 else f"FAILED (exit {proc.returncode})"
        typer.echo(f"-- {step.name}: {status}")
        if proc.returncode != 0:
            failed.append(step.name)
    if failed:
        typer.echo(f"dev check FAILED: {', '.join(failed)}", err=True)
        raise typer.Exit(int(ExitCode.FAILURE))
    typer.echo("dev check passed")
