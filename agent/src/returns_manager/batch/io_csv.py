"""Reads the two seller-supplied input files and joins them on `unit_id`.

Before-file columns: record_id,unit_id,org_id,order_id,ordered_sku,ordered_asin,
identity_match,parts_list,time,photo_ref[,category][,list_price | ,list_price_minor]
Returned-file columns: record_id,unit_id,org_id,order_id,ordered_sku,ordered_asin,
returned_photo_ref,time

Every listed column must be present. `record_id` and `unit_id` must also have a value on every
row; any other blank cell stays blank. Nothing is filled in: a blank ID is reported by the
sold-vs-returned check as "not checked", never as a match.

The optional unit price is `list_price` in rupees (e.g. `1299.50`, converted to 129950 paise) or
`list_price_minor` in paise (e.g. `129950`). A row without one uses the batch's configured default
price, and that row is marked `value_source=synthetic_default` so it is never shown as real.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
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

# Where a row's list price came from (output column `value_source`).
VALUE_SOURCE_CSV = "csv_list_price"
VALUE_SOURCE_DEFAULT = "synthetic_default"


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
    list_price_minor: int | None = None  # from the CSV only; None means "not supplied"


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


def parse_list_price(row: dict[str, str], filename: str, line: int) -> int | None:
    """The row's list price in minor units (paise), or None when neither price column has a
    value. `list_price` is rupees with at most 2 decimals; `list_price_minor` is whole paise."""
    rupees = (row.get("list_price") or "").strip()
    paise = (row.get("list_price_minor") or "").strip()
    from_rupees: int | None = None
    from_paise: int | None = None
    if rupees:
        try:
            amount = Decimal(rupees)
        except InvalidOperation:
            amount = Decimal("NaN")
        if not amount.is_finite() or amount < 0 or amount != amount.quantize(Decimal("0.01")):
            raise CsvInputError(
                filename,
                f"not a price in rupees with at most 2 decimals: {rupees!r}",
                line=line,
                column="list_price",
            )
        from_rupees = int(amount * 100)
    if paise:
        if not paise.isdigit():
            raise CsvInputError(
                filename, f"not a whole number of paise: {paise!r}", line=line, column="list_price_minor"
            )
        from_paise = int(paise)
    if from_rupees is not None and from_paise is not None and from_rupees != from_paise:
        raise CsvInputError(
            filename,
            f"list_price {rupees} (= {from_rupees} paise) disagrees with list_price_minor {from_paise}",
            line=line,
            column="list_price_minor",
        )
    return from_paise if from_paise is not None else from_rupees


def _rows(text: str, required: set[str], filename: str) -> list[tuple[int, dict[str, str]]]:
    """(line, row) for every non-empty data row, after checking the header and the required
    values. Line numbers are CSV lines as a spreadsheet shows them (the header is line 1)."""
    reader = csv.DictReader(io.StringIO(text, newline=""))
    check_columns(reader.fieldnames, required, filename)
    rows: list[tuple[int, dict[str, str]]] = []
    line = reader.line_num + 1
    for raw in reader:
        row = {k: (v or "").strip() for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)}
        if any(row.values()):
            for column in REQUIRED_VALUE_COLUMNS:
                if not row.get(column):
                    raise CsvInputError(filename, "required value is blank", line=line, column=column)
            rows.append((line, row))
        line = reader.line_num + 1
    return rows


def parse_before_csv(text: str, filename: str) -> dict[str, BeforeRow]:
    """Returns {unit_id: BeforeRow}. Later rows for the same unit_id overwrite earlier ones.
    Raises CsvInputError on a missing column or a blank record_id/unit_id."""
    by_unit: dict[str, BeforeRow] = {}
    for line, row in _rows(text, REQUIRED_BEFORE_COLUMNS, filename):
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
            list_price_minor=parse_list_price(row, filename, line),
        )
    return by_unit


def parse_returned_csv(text: str, filename: str) -> list[ReturnedRow]:
    """Raises CsvInputError on a missing column or a blank record_id/unit_id."""
    rows: list[ReturnedRow] = []
    for _line, row in _rows(text, REQUIRED_RETURNED_COLUMNS, filename):
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
    "auto_disapproved",  # "true" only for a proven ID or image-identity mismatch
    "photo_refs",
    "captured_at",
    "sold_vs_returned_id_check",
    "failure_reason",  # why a row failed open (empty on a real model + engine result)
    "value_source",  # csv_list_price, or synthetic_default when the CSV gave no price
    "requires_review",  # "true" when the engine or pipeline wants a person (review or sign-off)
    "rationale",  # plain-language summary of the evidence and the engine's rule (batch/runner.py)
]


def write_output_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in OUTPUT_FIELDNAMES})
