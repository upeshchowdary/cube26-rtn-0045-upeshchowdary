"""Test exact rubric quote substring matching against extracted pages."""

import json
import re

import pytest
import yaml

from returns_manager.config import REPO_ROOT

RUBRICS_DIR = REPO_ROOT / "reference" / "rubrics" / "amazon.co.uk"


def _clean(t: str) -> str:
    # De-hyphenate linebreaks (e.g. non-\nessential -> non-essential)
    t = re.sub(r"-\s*\n\s*", "-", t)
    # Collapse all whitespace
    return " ".join(t.split())


def _is_substring(quote: str, page_text: str) -> bool:
    if quote in page_text:
        return True
    return _clean(quote) in _clean(page_text)


@pytest.fixture(scope="module")
def extracted_pages() -> dict[int, str]:
    cache_file = RUBRICS_DIR / "_extracted_pages.json"
    assert cache_file.exists(), f"{cache_file} missing; run rubric extract first"
    raw = json.loads(cache_file.read_text(encoding="utf-8"))
    return {int(k): v for k, v in raw.items()}


def test_rubric_quotes_are_exact_substrings(extracted_pages: dict[int, str]) -> None:
    rubric_files = list(RUBRICS_DIR.glob("*.yaml"))
    assert len(rubric_files) >= 6, f"expected at least 6 rubrics, found {len(rubric_files)}"

    for f in rubric_files:
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        cat = data["category_key"]
        source_pages = data["source_pages"]
        combined_text = " ".join(extracted_pages[p] for p in source_pages)

        for g in data.get("grades", []):
            quote = g["text"]
            assert _is_substring(quote, combined_text), (
                f"[{cat}] Grade quote not in pages {source_pages}: {quote[:60]!r}"
            )

        for u in data.get("unacceptable_conditions", []):
            quote = u["text"]
            assert _is_substring(quote, combined_text), (
                f"[{cat}] Unacceptable quote not in pages {source_pages}: {quote[:60]!r}"
            )
