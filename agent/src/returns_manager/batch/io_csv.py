"""Reads the two seller-supplied input files and joins them on `unit_id`.

Before-file columns: record_id,unit_id,org_id,order_id,ordered_sku,ordered_asin,
identity_match,parts_list,time,photo_ref[,category]
Returned-file columns: record_id,unit_id,org_id,order_id,ordered_sku,ordered_asin,
returned_photo_ref,time

Every listed column must be present. `record_id` and `unit_id` must also have a value on every
row; any other blank cell stays blank. Nothing is filled in: a blank ID is reported by the
sold-vs-returned check as "not checked", never as a match.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REQUIRED_BEFORE_COLUMNS = {
    "record_id",
    "unit_id",
    "org_id",
    "order_id",
    "ordered_sku",
    "ordered_asin",
    "identity_match",
    "parts_list",
    "time",
    "photo_ref",
}
REQUIRED_RETURNED_COLUMNS = {
    "record_id",
    "unit_id",
    "org_id",
    "order_id",
    "ordered_sku",
    "ordered_asin",
    "returned_photo_ref",
    "time",
}
# Columns that must have a value on every row: they identify the record and join the two files.
REQUIRED_VALUE_COLUMNS = ("record_id", "unit_id")


class CsvInputError(ValueError):
    """A malformed upload. The message names the file, and the line and column when there is
    one, so the uploader can fix the file (the API returns it as a 400)."""

    def __init__(
        self, filename: str, message: str, *, line: int | None = None, column: str | None = None
    ) -> None:
        where = [filename]
        if line is not None:
            where.append(f"line {line}")
        if column is not None:
            where.append(f"column {column!r}")
        super().__init__(f"{', '.join(where)}: {message}")
        self.filename = filename
        self.line = line
        self.column = column


@dataclass(frozen=True)
class BeforeRow:
    record_id: str
    unit_id: str
    org_id: str
    order_id: str
    ordered_sku: str
    ordered_asin: str
    identity_match: str  # as given in the before-file; blank when the file left it blank
    parts_list: str
    time: str
    photo_ref: str
    category: str | None = None


@dataclass(frozen=True)
class ReturnedRow:
    record_id: str
    unit_id: str
    org_id: str
    order_id: str
    ordered_sku: str
    ordered_asin: str
    returned_photo_refs: tuple[str, ...]
    time: str


def check_columns(fieldnames: Sequence[str] | None, required: set[str], filename: str) -> None:
    have = set(fieldnames or [])
    missing = required - have
    if missing:
        raise CsvInputError(filename, f"missing required column(s): {', '.join(sorted(missing))}")


def _rows(text: str, required: set[str], filename: str) -> list[dict[str, str]]:
    """Every non-empty data row, after checking the header and the required values. Line
    numbers in errors are CSV lines as a spreadsheet shows them (the header is line 1)."""
    reader = csv.DictReader(io.StringIO(text, newline=""))
    check_columns(reader.fieldnames, required, filename)
    rows: list[dict[str, str]] = []
    line = reader.line_num + 1
    for raw in reader:
        row = {k: (v or "").strip() for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)}
        if any(row.values()):
            for column in REQUIRED_VALUE_COLUMNS:
                if not row.get(column):
                    raise CsvInputError(filename, "required value is blank", line=line, column=column)
            rows.append(row)
        line = reader.line_num + 1
    return rows


def parse_before_csv(text: str, filename: str) -> dict[str, BeforeRow]:
    """Returns {unit_id: BeforeRow}. Later rows for the same unit_id overwrite earlier ones.
    Raises CsvInputError on a missing column or a blank record_id/unit_id."""
    by_unit: dict[str, BeforeRow] = {}
    for row in _rows(text, REQUIRED_BEFORE_COLUMNS, filename):
        category = row.get("category") or None
        by_unit[row["unit_id"]] = BeforeRow(
            record_id=row["record_id"],
            unit_id=row["unit_id"],
            org_id=row.get("org_id", ""),
            order_id=row.get("order_id", ""),
            ordered_sku=row.get("ordered_sku", ""),
            ordered_asin=row.get("ordered_asin", ""),
            identity_match=row.get("identity_match", ""),
            parts_list=row.get("parts_list", ""),
            time=row.get("time", ""),
            photo_ref=row.get("photo_ref", ""),
            category=category.lower() if category else None,
        )
    return by_unit


def parse_returned_csv(text: str, filename: str) -> list[ReturnedRow]:
    """Raises CsvInputError on a missing column or a blank record_id/unit_id."""
    rows: list[ReturnedRow] = []
    for row in _rows(text, REQUIRED_RETURNED_COLUMNS, filename):
        refs = tuple(u.strip() for u in row.get("returned_photo_ref", "").split(";") if u.strip())
        rows.append(
            ReturnedRow(
                record_id=row["record_id"],
                unit_id=row["unit_id"],
                org_id=row.get("org_id", ""),
                order_id=row.get("order_id", ""),
                ordered_sku=row.get("ordered_sku", ""),
                ordered_asin=row.get("ordered_asin", ""),
                returned_photo_refs=refs,
                time=row.get("time", ""),
            )
        )
    return rows


def read_before_csv(path: Path) -> dict[str, BeforeRow]:
    return parse_before_csv(path.read_text(encoding="utf-8-sig"), path.name)


def read_returned_csv(path: Path) -> list[ReturnedRow]:
    return parse_returned_csv(path.read_text(encoding="utf-8-sig"), path.name)


OUTPUT_FIELDNAMES = [
    "record_id",
    "unit_id",
    "org_id",
    "order_id",
    "ordered_sku",
    "ordered_asin",
    "identity_match",  # carried forward from the before-file, never re-derived (F-024)
    "photo_identity_match",  # the model's own verdict on the returned photo(s); uncertain if none
    "parts_list",
    "parts_missing",
    "observed_state",
    "amazon_condition",
    "operator_disposition",  # the engine route only if auto-approved; otherwise pending_review
    "agent_disposition",  # the engine's recommendation (empty when it made none)
    "auto_approved",  # "true" only per batch/auto_approve.py; never recomputed by the UI
    "photo_refs",
    "captured_at",
    "sold_vs_returned_id_check",
    "failure_reason",  # why a row failed open (empty on a real model + engine result)
]


def write_output_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in OUTPUT_FIELDNAMES})
