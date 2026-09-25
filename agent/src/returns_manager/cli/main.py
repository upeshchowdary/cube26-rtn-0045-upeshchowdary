"""`returns-manager` CLI (build prompt §20).

Every command calls the service layer; no business logic lives here. Commands whose phase is not built yet
are registered so `--help` shows the whole tree, and they exit 1 saying which phase builds them.
"""

from __future__ import annotations

import sys

import typer

from returns_manager import __version__
from returns_manager.cli import (
    audit_commands,
    chain_commands,
    dev,
    inspect_commands,
    intake_commands,
    job_commands,
    p1_commands,
    reference_commands,
    review_commands,
)
from returns_manager.errors import ExitCode, NotBuiltYet, ReturnsManagerError

app = typer.Typer(
    name="returns-manager",
    help="Returns Manager: evidence-backed returns inspection "
    "(identity, completeness, condition, disposition).",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    add_completion=False,
)

_STUB_SETTINGS = {"allow_extra_args": True, "ignore_unknown_options": True}


def _stub(group: typer.Typer, name: str, phase: str, help_text: str, full_name: str) -> None:
    def command(ctx: typer.Context) -> None:
        raise NotBuiltYet(full_name, phase)

    command.__doc__ = f"[{phase}, not built yet] {help_text}"
    group.command(name, context_settings=_STUB_SETTINGS)(command)


# (group, command, phase, help). Group None = top-level command.
_PLANNED: list[tuple[str | None, str, str, str]] = [
    ("evidence", "show", "P10", "Show a unit's evidence record."),
    ("evidence", "export", "P10", "Export evidence records (JSONL or flat CSV)."),
    ("economics", "report", "P11", "Unit-economics report (paid-equivalent cost)."),
    ("eval", "seal", "P12", "Hash and seal the eval set (quota checks)."),
    ("eval", "run", "P12", "Run the sealed eval (quota- and spend-guarded)."),
    ("eval", "report", "P12", "Generate the eval report for a run."),
    (None, "load-test", "P13", "Load test in replay or live mode."),
    ("openapi", "export", "P10", "Export OpenAPI JSON."),
    ("contract", "build", "P10", "Build contract schemas and examples."),
    ("contract", "check", "P10", "Check contract compatibility."),
    ("mcp", "serve", "P10", "Serve the read-only MCP server."),
]

_GROUP_HELP = {
    "db": "Database migrations.",
    "reference": "Reference data (product cards, rubrics, policies).",
    "rubric": "Condition-guideline rubric extraction.",
    "catalogue": "Organiser catalogue import.",
    "seed": "Demo data.",
    "keys": "Scoped API keys.",
    "quota": "Gemini free-tier daily request budgets.",
    "audit": "Blind audit reviewer.",
    "jobs": "Durable job queue.",
    "review": "Human review and sign-off.",
    "evidence": "Evidence records.",
    "chain": "Per-unit event chains.",
    "ledger": "Per-org ledger and anchors.",
    "controls": "Kill-switch controls.",
    "simulate": "What-if simulation.",
    "economics": "Unit economics.",
    "eval": "Evaluation tooling (never reads sealed data outside `eval run`).",
    "openapi": "OpenAPI export.",
    "contract": "Cross-pod evidence contract.",
    "mcp": "MCP server.",
    "api": "REST API server.",
    "dev": "Developer checks.",
}

_groups: dict[str, typer.Typer] = {}


def _group(name: str) -> typer.Typer:
    if name not in _groups:
        sub = typer.Typer(help=_GROUP_HELP.get(name, ""), no_args_is_help=True)
        _groups[name] = sub
        app.add_typer(sub, name=name)
    return _groups[name]


def _register() -> None:
    built = {
        "dev": dev.app,
        "db": p1_commands.db_app,
        "keys": p1_commands.keys_app,
        "controls": p1_commands.controls_app,
        "seed": p1_commands.seed_app,
        "api": p1_commands.api_app,
        "reference": reference_commands.reference_app,
        "rubric": reference_commands.rubric_app,
        "catalogue": reference_commands.catalogue_app,
        "jobs": job_commands.jobs_app,
        "quota": inspect_commands.quota_app,
        "simulate": inspect_commands.simulate_app,
        "chain": chain_commands.chain_app,
        "ledger": chain_commands.ledger_app,
        "review": review_commands.review_app,
        "audit": audit_commands.audit_app,
    }
    for name, sub in built.items():
        _groups[name] = sub
        app.add_typer(sub, name=name, help=_GROUP_HELP[name])
    app.command("capture")(intake_commands.capture_command)
    app.command("worker")(job_commands.worker_command)
    app.command("inspect")(inspect_commands.inspect_command)
    for group, name, phase, help_text in _PLANNED:
        if group in _groups:
            cmds = getattr(_groups[group], "registered_commands", [])
            if any(c.name == name for c in cmds):
                continue
        if group is None:
            _stub(app, name, phase, help_text, name)
        else:
            _stub(_group(group), name, phase, help_text, f"{group} {name}")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"returns-manager {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show the version and exit."
    ),
) -> None:
    """Returns Manager CLI."""


_register()


def run(argv: list[str] | None = None) -> int:
    """Run the CLI and return an exit code (used by `main` and by tests)."""
    # Standalone mode: Typer prints usage errors itself and exits 2 (§20 "usage error").
    # Our own errors propagate out of it and are mapped to their exit codes here.
    try:
        app(args=argv, prog_name="returns-manager")
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return int(ExitCode.OK)
        return code if isinstance(code, int) else int(ExitCode.FAILURE)
    except ReturnsManagerError as exc:
        typer.echo(f"error: {exc}", err=True)
        return int(exc.exit_code)
    return int(ExitCode.OK)


def main() -> None:
    sys.exit(run())
