#!/usr/bin/env python3
"""Local repository-boundary check. Run before every push (also a pre-commit hook and part of `dev check`).

It mirrors the intent of the organiser CI guard (`.github/scripts/submission-guard.sh`), adapted to this
fork's layout (build log, finding F-007: the build lives at the fork root, not `submissions/<user>/`):

1. The working branch is named after the GitHub username (lowercase), and is never `main`.
2. No change touches an organiser-owned path (PROTECTED below). Changing one needs a recorded decision in
   `build-log.md` and an edit of this list in the same commit.
3. No change adds a forbidden file (`.env` with secrets, PDFs such as Amazon's guideline document, keys).
4. No changed file is larger than 5 MB (GitHub warns at 50 MB; the build prompt caps files at 5 MB).

Standard library only, so it runs outside the project virtualenv. Exit 0 = ok, 1 = violations.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

GITHUB_USERNAME = "upeshchowdary"
BASE_REF = "origin/main"
MAX_BYTES = 5 * 1024 * 1024

# Organiser-owned paths in the fork (exact files, or directories ending with "/"). Compared lowercased.
PROTECTED: tuple[str, ...] = (
    ".github/",
    "data/",
    "submissions/",
    ".gitignore",
    "README.md",
    "RULES.md",
    "GITHUB-GUIDE.md",
)

FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("environment file with secrets", re.compile(r"(^|/)\.env(\.(?!example$)[^/]*)?$")),
    (
        "PDF (source documents are downloaded and hash-verified, never committed)",
        re.compile(r"\.pdf$"),
    ),
    ("private key material", re.compile(r"\.(pem|key|p12|pfx)$")),
)


@dataclass(frozen=True)
class Violation:
    path: str | None
    reason: str

    def __str__(self) -> str:
        return f"{self.path}: {self.reason}" if self.path else self.reason


def is_protected(path: str) -> bool:
    p = PurePosixPath(path).as_posix().lower()
    for entry in PROTECTED:
        e = entry.lower()
        if e.endswith("/"):
            if p.startswith(e):
                return True
        elif p == e:
            return True
    return False


def find_violations(
    branch: str,
    changed: Iterable[str],
    sizes: Mapping[str, int],
    username: str = GITHUB_USERNAME,
) -> list[Violation]:
    out: list[Violation] = []
    if branch.lower() != username.lower():
        out.append(
            Violation(
                None,
                f"branch '{branch}' must be named exactly '{username.lower()}' (never main)",
            )
        )
    elif branch != branch.lower():
        out.append(Violation(None, f"branch '{branch}' must be lowercase"))
    for path in sorted(set(changed)):
        if is_protected(path):
            out.append(Violation(path, "organiser-owned path; must not be modified"))
        for label, pattern in FORBIDDEN_PATTERNS:
            if pattern.search(path.lower()):
                out.append(Violation(path, f"forbidden file: {label}"))
        size = sizes.get(path)
        if size is not None and size > MAX_BYTES:
            out.append(Violation(path, f"{size} bytes exceeds the 5 MB per-file cap"))
    return out


def _git(repo: Path, *args: str) -> str:
    for attempt in range(3):
        try:
            return subprocess.run(  # fixed git argv, no shell
                ["git", *args],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            ).stdout
        except subprocess.CalledProcessError as exc:
            # Handle transient Windows 0xC0000005 native crash
            if attempt == 2 or exc.returncode not in (3221225477, -1073741819):
                raise
    raise RuntimeError("unreachable")


def changed_files(repo: Path, base: str) -> list[str]:
    """Committed changes since the merge-base with `base`, plus staged, unstaged and untracked files."""
    files: set[str] = set()
    merge_base = _git(repo, "merge-base", base, "HEAD").strip()
    for args in (
        ("diff", "--name-only", f"{merge_base}...HEAD"),
        ("diff", "--name-only", "--cached"),
        ("diff", "--name-only"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        files.update(line for line in _git(repo, *args).splitlines() if line)
    return sorted(files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else None
    )
    parser.add_argument(
        "--base",
        default=BASE_REF,
        help="base ref to diff against (default: origin/main)",
    )
    parser.add_argument("--username", default=GITHUB_USERNAME)
    parser.add_argument(
        "files",
        nargs="*",
        help="check only these paths (pre-commit passes staged files)",
    )
    args = parser.parse_args(argv)

    repo = Path(_git(Path.cwd(), "rev-parse", "--show-toplevel").strip())
    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    changed = args.files or changed_files(repo, args.base)
    sizes = {f: (repo / f).stat().st_size for f in changed if (repo / f).is_file()}

    violations = find_violations(branch, changed, sizes, args.username)
    if violations:
        print("boundary check FAILED:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1
    print(
        f"boundary check ok: branch '{branch}', {len(changed)} changed file(s), none organiser-owned"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
