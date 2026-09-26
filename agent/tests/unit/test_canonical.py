"""RFC 8785 canonical JSON: golden vectors (verify-first item for the `rfc8785` package, §0.7 / §13.1).

Expected canonical bytes are written by hand from RFC 8785, not produced by the code under test; the
golden hashes are SHA-256 of those literal bytes.
"""

from __future__ import annotations

import hashlib

import pytest

from returns_manager.canonical.hashing import normalize_text, sha256_jcs, sha256_text
from returns_manager.canonical.jcs import CanonicalizationError, canonical_bytes

GOLDEN: list[tuple[str, object, bytes]] = [
    ("key order", {"b": 1, "a": 2, "c": {"z": True, "y": None}}, b'{"a":2,"b":1,"c":{"y":null,"z":true}}'),
    ("no whitespace, arrays keep order", [3, 1, [2, "x"]], b'[3,1,[2,"x"]]'),
    ("non-ASCII stays UTF-8", {"sku": "café"}, '{"sku":"café"}'.encode()),
    # RFC 8785 §3.2.3 sorts keys by UTF-16 code units: U+1F600 (surrogate D83D) sorts BEFORE U+FF61,
    # although its code point is larger. A naive code-point sort would get this wrong.
    ("UTF-16 key order", {"｡": 2, "\U0001f600": 1}, '{"\U0001f600":1,"｡":2}'.encode()),
    ("escapes", {"t": 'a"b\\c\n\u000f'}, b'{"t":"a\\"b\\\\c\\n\\u000f"}'),
    (
        "largest safe integer",
        {"n": 2**53 - 1, "m": -(2**53 - 1)},
        b'{"m":-9007199254740991,"n":9007199254740991}',
    ),
    (
        "basis points and minor units",
        {"confidence_bp": 9300, "amount_minor": 199900, "currency": "INR"},
        b'{"amount_minor":199900,"confidence_bp":9300,"currency":"INR"}',
    ),
]


@pytest.mark.parametrize(("name", "value", "expected"), GOLDEN, ids=[g[0] for g in GOLDEN])
def test_golden_vectors(name: str, value: object, expected: bytes) -> None:
    assert canonical_bytes(value) == expected
    assert sha256_jcs(value) == hashlib.sha256(expected).hexdigest()


def test_golden_hash_is_stable() -> None:
    # Fixed input -> fixed hash, committed: any change to canonicalisation breaks this.
    value = {"event_type": "return_created", "seq": 1, "org_id": "org_demo_alpha", "unit_id": "UNIT-0014"}
    assert (
        sha256_jcs(value)
        == hashlib.sha256(
            b'{"event_type":"return_created","org_id":"org_demo_alpha","seq":1,"unit_id":"UNIT-0014"}'
        ).hexdigest()
    )


@pytest.mark.parametrize("value", [2**53, -(2**53), 10**20])
def test_integers_outside_ijson_range_are_rejected(value: int) -> None:
    with pytest.raises(CanonicalizationError):
        canonical_bytes({"n": value})


@pytest.mark.parametrize("value", [0.5, {"a": [1, 2.0]}, {"x": {"y": float("nan")}}])
def test_floats_are_rejected_anywhere(value: object) -> None:
    with pytest.raises(CanonicalizationError, match="float"):
        canonical_bytes(value)


def test_non_string_keys_and_unsupported_types_are_rejected() -> None:
    with pytest.raises(CanonicalizationError):
        canonical_bytes({1: "a"})
    with pytest.raises(CanonicalizationError):
        canonical_bytes({"a": object()})


def test_no_unicode_normalisation() -> None:
    # JCS hashes strings exactly as given: NFC "é" and NFD "e + combining acute" differ.
    assert sha256_jcs({"s": "é"}) != sha256_jcs({"s": "é"})


def test_text_hash_ignores_line_ending_style() -> None:
    assert normalize_text(b"a\r\nb\rc\n") == b"a\nb\nc\n"
    assert sha256_text(b"line1\r\nline2\r\n") == sha256_text(b"line1\nline2\n")
