"""P0: scripts/check_boundary.py enforces branch name, organiser files, forbidden files and the size cap."""

from __future__ import annotations

import importlib.util
import sys
from types import ModuleType

import pytest

from returns_manager.config import REPO_ROOT


@pytest.fixture(scope="module")
def cb() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_boundary", REPO_ROOT / "scripts" / "check_boundary.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations via sys.modules
    spec.loader.exec_module(module)
    return module


def test_clean_change_set_passes(cb: ModuleType) -> None:
    files = ["agent/src/returns_manager/config.py", "build-log.md", ".env.example", "decisions/ADR-001-x.md"]
    assert cb.find_violations("upeshchowdary", files, {}) == []


@pytest.mark.parametrize("branch", ["main", "feature/x", "UpeshChowdary"])
def test_wrong_branch_fails(cb: ModuleType, branch: str) -> None:
    assert cb.find_violations(branch, [], {}, "upeshchowdary")


@pytest.mark.parametrize(
    "path",
    [
        "README.md",
        "RULES.md",
        "GITHUB-GUIDE.md",
        ".gitignore",
        "data/returns_sample.csv",
        ".github/scripts/submission-guard.sh",
        "submissions/_TEMPLATE/README.md",
        "Data/README.md",
    ],
)
def test_organiser_paths_are_protected(cb: ModuleType, path: str) -> None:
    v = cb.find_violations("upeshchowdary", [path], {})
    assert any("organiser-owned" in x.reason for x in v)


def test_nested_readme_and_gitignore_are_ours(cb: ModuleType) -> None:
    assert cb.find_violations("upeshchowdary", ["agent/README.md", "agent/.gitignore"], {}) == []


@pytest.mark.parametrize(
    "path", [".env", "agent/.env", ".env.local", ".env.demo-users", "reference/guidelines.pdf", "keys/x.pem"]
)
def test_forbidden_files(cb: ModuleType, path: str) -> None:
    assert any("forbidden" in x.reason for x in cb.find_violations("upeshchowdary", [path], {}))


def test_env_example_is_allowed(cb: ModuleType) -> None:
    assert cb.find_violations("upeshchowdary", [".env.example"], {}) == []


def test_size_cap(cb: ModuleType) -> None:
    big = 5 * 1024 * 1024 + 1
    v = cb.find_violations("upeshchowdary", ["fixtures/units/U/1.jpg"], {"fixtures/units/U/1.jpg": big})
    assert any("5 MB" in x.reason for x in v)
