from __future__ import annotations

import re
from pathlib import Path


def test_repo_has_no_machine_specific_paths() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    bad = []
    patterns = re.compile(
        r"(?:C:\\Users\\|C:/Users/|(?<![A-Za-z])/(?:Users|home|mnt)/)",
        re.IGNORECASE,
    )
    excluded_dirs = {
        ".git",
        ".venv",
        ".pytest_cache",
        "node_modules",
        "dist",
        ".hypothesis",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
    }

    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if path.name == "test_portability.py":
            continue
        if any(part in excluded_dirs for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if patterns.search(text):
            bad.append(str(path.relative_to(repo_root)))

    assert not bad, f"Machine-specific paths remain in the repo: {bad}"
