"""Migration discovery/checksums and storage key layout (no database)."""

from __future__ import annotations

from pathlib import Path

import pytest

from returns_manager.db.migrate import MigrationError, compare, discover
from returns_manager.db.tenant import InvalidOrgId, validate_org_id
from returns_manager.storage.photos import photo_object_key


def test_repository_migrations_are_contiguous() -> None:
    migrations = discover()
    assert [m.version for m in migrations][:3] == ["0001", "0002", "0003"]
    assert all(len(m.checksum) == 64 for m in migrations)


def test_checksum_ignores_line_endings(tmp_path: Path) -> None:
    (tmp_path / "0001_a.sql").write_bytes(b"SELECT 1;\nSELECT 2;\n")
    lf = discover(tmp_path)[0].checksum
    (tmp_path / "0001_a.sql").write_bytes(b"SELECT 1;\r\nSELECT 2;\r\n")
    assert discover(tmp_path)[0].checksum == lf


def test_gaps_and_bad_names_are_rejected(tmp_path: Path) -> None:
    (tmp_path / "0001_a.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "0003_c.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(MigrationError):
        discover(tmp_path)
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "1_x.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(MigrationError):
        discover(bad)


def test_compare_detects_changed_and_missing(tmp_path: Path) -> None:
    (tmp_path / "0001_a.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "0002_b.sql").write_text("SELECT 2;", encoding="utf-8")
    files = discover(tmp_path)
    states = {s.version: s.state for s in compare(files, {"0001": files[0].checksum})}
    assert states == {"0001": "applied", "0002": "pending"}
    states = {s.version: s.state for s in compare(files, {"0001": "0" * 64, "0009": "1" * 64})}
    assert states == {"0001": "CHANGED", "0002": "pending", "0009": "MISSING_FILE"}


def test_photo_keys_are_org_prefixed_and_unguessable() -> None:
    k1 = photo_object_key("org_demo_alpha", "01JRET", "image/jpeg")
    k2 = photo_object_key("org_demo_alpha", "01JRET", "image/jpeg")
    assert k1.startswith("org/org_demo_alpha/returns/01JRET/")
    assert k1.endswith(".jpg")
    assert k1 != k2
    assert len(k1.rsplit("/", 1)[1]) == len("xxxxxxxx-xxxx-4xxx-xxxx-xxxxxxxxxxxx.jpg")


@pytest.mark.parametrize("org", ["", "global", "Org_A", "org/../b", "a", "x" * 70])
def test_invalid_org_ids_are_rejected(org: str) -> None:
    with pytest.raises(InvalidOrgId):
        validate_org_id(org)
