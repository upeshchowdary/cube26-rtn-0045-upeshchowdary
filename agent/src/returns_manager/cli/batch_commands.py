"""CLI: `batch process` - standalone image-URL batch processing (no database)."""

from __future__ import annotations

from pathlib import Path

import typer

from returns_manager.batch.cards import DEFAULT_LIST_PRICE_MINOR
from returns_manager.batch.io_csv import write_output_csv
from returns_manager.batch.runner import run_batch_sync
from returns_manager.config import get_settings
from returns_manager.llm.gemini_client import GeminiModelClient

batch_app = typer.Typer(
    help="Standalone batch processing of return records with image URLs.", no_args_is_help=True
)


@batch_app.command("process")
def process_command(
    before: Path = typer.Option(..., "--before", help="Before-sale CSV: one row per unit."),
    returned: Path = typer.Option(..., "--returned", help="Returned-item CSV: one row per return."),
    out: Path = typer.Option(..., "--out", help="Output CSV path (returns_sample.csv shape)."),
    default_category: str | None = typer.Option(
        None,
        "--default-category",
        help="Category to use when a before-row has no 'category' column "
        "(electronics | home_kitchen | toys_games | beauty_topical | pet | grocery_ingestible).",
    ),
    list_price_minor: int = typer.Option(
        DEFAULT_LIST_PRICE_MINOR,
        "--list-price-minor",
        help="Default list price (paise) for rows whose before-file has no list_price / "
        "list_price_minor. Those rows are marked value_source=synthetic_default.",
    ),
    max_requests: int | None = typer.Option(
        None,
        "--max-requests",
        help="Hard cap on live model requests for this run; every round trip and retry counts. "
        "A request past the cap is refused before it is sent.",
    ),
) -> None:
    """Process a before/returned CSV pair and write one output row per return.

    Downloads every photo URL, runs the real judgment session and deterministic pipeline
    per return, and writes an output CSV in the same shape as data/returns_sample.csv
    (identity_match is carried forward from the before-file, not re-derived).
    """
    settings = get_settings()
    settings.require("gemini_api_key")
    assert settings.gemini_api_key is not None
    client = GeminiModelClient(settings.gemini_api_key.get_secret_value(), settings.rm_model_timeout_s)

    rows, _details_by_record_id, summary = run_batch_sync(
        before_path=before,
        returned_path=returned,
        settings=settings,
        client=client,
        default_category=default_category,
        list_price_minor=list_price_minor,
        max_requests=max_requests,
    )
    write_output_csv(out, rows)

    typer.echo(
        f"{summary.total_rows} return(s): {summary.processed} processed, {summary.uncertain} uncertain"
    )
    typer.echo(f"live model requests used: {summary.live_requests}")
    for note in summary.notes:
        typer.echo(f"  - {note}")
    typer.echo(f"wrote {out}")
