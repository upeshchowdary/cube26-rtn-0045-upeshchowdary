"""The project docs state only what the code does (audit Stage 2 item 6).

- The rule table embedded in the docs is exactly `scripts/rule_table.py`'s output for the current engine.
- No §24 forbidden term, no fifth disposition and no "Gemini 2.5" appears in the docs.
- Every model ID the docs name is a configured default.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from types import ModuleType

import pytest

from returns_manager.config import REPO_ROOT, Settings

DOCS = ["ARCHITECTURE.md", "MASTER_PROJECT_PROMPT.md", "agent/README.md"]
DOCS_WITH_RULE_TABLE = ["ARCHITECTURE.md", "MASTER_PROJECT_PROMPT.md"]

# CLAUDE.md "Forbidden language (§24)", plus the audit's list for this pass.
FORBIDDEN = re.compile(
    r"immutable|tamper[- ]?proof|blockchain|\bfraud|counterfeit"
    r"|production[- ](ready|grade)|enterprise[- ]grade|real[- ]time|guarantee|100\s?%|0 flaws"
    r"|state[- ]of[- ]the[- ]art|certified|amazon[- ](approved|compliant)"
    r"|self[- ]improving|learns from overrides|works perfectly|fully functional|the ai decided",
    re.IGNORECASE,
)


@pytest.fixture(scope="module")
def rule_table() -> ModuleType:
    spec = importlib.util.spec_from_file_location("rule_table", REPO_ROOT / "scripts" / "rule_table.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _read(doc: str) -> str:
    return (REPO_ROOT / doc).read_text(encoding="utf-8")


@pytest.mark.parametrize("doc", DOCS_WITH_RULE_TABLE)
def test_embedded_rule_table_matches_the_engine(doc: str, rule_table: ModuleType) -> None:
    text = _read(doc)
    m = re.search(r"<!-- rule-table:start -->\n(.*?)<!-- rule-table:end -->", text, re.DOTALL)
    assert m, f"{doc} has no rule-table block"
    assert m.group(1) == rule_table.markdown(), f"{doc}: run `python scripts/rule_table.py` and paste it"


def test_rule_table_covers_every_rule_id_in_the_engine(rule_table: ModuleType) -> None:
    engine = (REPO_ROOT / "agent" / "src" / "returns_manager" / "disposition" / "engine.py").read_text(
        encoding="utf-8"
    )
    in_engine = set(re.findall(r'"(R\d+[a-z]?)"', engine)) | set(
        re.findall(r"#\s*(R\d+[a-z]?)\s*$", engine, re.M)
    )
    in_engine |= {s.split("_", 1)[0] for s in re.findall(r'"(S\d+_[a-z_]+)"', engine)}
    in_table = {row[0] for row in rule_table.rows()}
    assert in_engine == in_table


@pytest.mark.parametrize("doc", DOCS)
def test_docs_have_no_forbidden_terms(doc: str) -> None:
    hits = [
        f"{doc}:{n}: {line.strip()}"
        for n, line in enumerate(_read(doc).splitlines(), 1)
        if FORBIDDEN.search(line)
    ]
    assert hits == []


@pytest.mark.parametrize("doc", DOCS)
def test_docs_name_only_the_four_dispositions_and_no_old_model(doc: str) -> None:
    text = _read(doc)
    assert "wrong_product" not in text
    assert not re.search(r"gemini[- ]2\.5", text, re.IGNORECASE)
    assert "Open Box" not in text


@pytest.mark.parametrize("doc", DOCS)
def test_model_ids_in_docs_are_configured_defaults(doc: str) -> None:
    configured = {
        str(Settings.model_fields[f].default)
        for f in (
            "rm_judgment_model",
            "rm_judgment_fallback_model",
            "rm_escalation_model",
            "rm_audit_model",
            "rm_explainer_model",
        )
    }
    named = set(re.findall(r"gemini-[0-9][\w.\-]*[\w]", _read(doc)))
    assert named <= configured, named - configured
