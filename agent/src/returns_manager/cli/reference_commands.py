"""P2 CLI commands: reference, rubric, catalogue.

Each command only calls a service function; no business logic lives here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from returns_manager.config import get_settings
from returns_manager.db.pool import Database, run_async
from returns_manager.errors import ExitCode, VerificationFailed
from returns_manager.reference import extract, loader, validator

reference_app = typer.Typer(help="Reference data (product cards, rubrics, policies).", no_args_is_help=True)
rubric_app = typer.Typer(help="Condition-guideline rubric extraction.", no_args_is_help=True)
catalogue_app = typer.Typer(help="Organiser catalogue import.", no_args_is_help=True)


def _app_db() -> Database:
    settings = get_settings()
    settings.require("database_url")
    assert settings.database_url is not None
    return Database(settings.database_url.get_secret_value())


# ── reference ──────────────────────────────────────────────────────────


@reference_app.command("validate")
def reference_validate() -> None:
    """Validate every reference file against its schema and content hash."""
    v = validator.ReferenceValidator()
    try:
        v.run_all()
        typer.echo(f"reference validate ok: {len(v.validated_files)} file(s) valid")
    except VerificationFailed as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(int(ExitCode.VERIFICATION_FAILED)) from exc


@reference_app.command("hash")
def reference_hash() -> None:
    """Compute and refresh content_sha256 in all reference YAML files in-place."""
    updated = validator.hash_all_reference_files()
    typer.echo(f"updated content_sha256 on {len(updated)} file(s)")
    for path, sha in updated:
        typer.echo(f"  {path.name}: {sha[:12]}...")


@reference_app.command("load")
def reference_load() -> None:
    """Load reference data (rubrics, policies, products, components, images, orders) into the database."""

    async def go() -> dict[str, Any]:
        async with _app_db() as db:
            return await loader.load_all(db)

    result = run_async(go)
    typer.echo("reference load complete:")
    typer.echo(f"  rubric_snapshots: {result['rubric_snapshots']}")
    typer.echo(f"  category_policies: {result['category_policies']}")
    for org, count in result["products_by_org"].items():
        typer.echo(f"  products ({org}): {count}")
    typer.echo(f"  orders: {result['orders']}")


# ── rubric ─────────────────────────────────────────────────────────────


@rubric_app.command("extract")
def rubric_extract(
    source: str = typer.Option(
        "amazon-uk-condition-guidelines-pdf",
        "--source",
        "-s",
        help="Source identifier from reference/sources.yaml",
    ),
) -> None:
    """Download, hash-verify and extract condition-guideline rubric snapshots from an authoritative PDF."""
    try:
        written = extract.extract_and_write_rubrics(source_id=source)
        typer.echo(f"rubric extract ok: extracted {len(written)} category snapshot(s) from {source}")
        for cat, path in written.items():
            typer.echo(f"  {cat}: {path}")
    except Exception as exc:
        typer.echo(f"rubric extract failed: {exc}", err=True)
        raise typer.Exit(int(ExitCode.FAILURE)) from exc


# ── catalogue ──────────────────────────────────────────────────────────


@catalogue_app.command("import")
def catalogue_import(
    file_path: Path = typer.Option(..., "--file", "-f", help="Path to organiser-provided shared catalogue"),
    org_id: str = typer.Option("org_demo_alpha", "--org", "-o", help="Target organization ID"),
) -> None:
    """Import an organiser-provided shared catalogue with provenance tracking."""
    if not file_path.exists():
        typer.echo(f"catalogue file {file_path} does not exist", err=True)
        raise typer.Exit(int(ExitCode.USAGE))
    typer.echo(f"catalogue import for {org_id} from {file_path.name}: 0 rows imported (template/stub)")
