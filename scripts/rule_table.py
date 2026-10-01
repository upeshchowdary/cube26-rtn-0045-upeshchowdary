"""Print the disposition rule table, generated from agent/src/returns_manager/disposition/engine.py.

The docs (ARCHITECTURE.md, MASTER_PROJECT_PROMPT.md) embed this output between
`<!-- rule-table:start -->` and `<!-- rule-table:end -->`; a unit test fails if they drift.
Regenerate with:  python scripts/rule_table.py

It reads the engine's source with `ast` (nothing is imported or executed) and lists, in source order:
- Step 1 gates: `gate = ("Rxx", reason)`       -> no recommendation, review required
- Step 2 review flags: `review... # Rxx` lines   -> review flag, route unchanged
- Step 3 routes: `_Route("Rxx", route, ...)` and `_salvage_route(inp, "Rxx", ...)`
- Sign-off rules: `signoff.append("Sxx_...")`
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

# How engine.decide() resolves each gate (directives 3, 4, 9). Gates not listed have no route.
GATE_OUTCOMES = {
    "R02": "dispose + S01 sign-off if clearly empty; else provisional route (review required)",
    "R03": "dispose + S01 sign-off (review required)",
    "R03b": "provisional route from the other evidence (review required)",
    "R05b": "no recommendation (review required)",
}

ENGINE = (
    Path(__file__).resolve().parents[1]
    / "agent"
    / "src"
    / "returns_manager"
    / "disposition"
    / "engine.py"
)


def _text(node: ast.expr) -> str:
    if isinstance(node, ast.Constant):
        return str(node.value)
    return ast.unparse(node)


def _conditions(parents: dict[ast.AST, ast.AST], node: ast.AST) -> str:
    """The `if` tests enclosing `node` inside its function, outermost first."""
    tests: list[str] = []
    child: ast.AST = node
    cur = parents.get(node)
    while cur is not None and not isinstance(cur, ast.FunctionDef):
        if isinstance(cur, ast.If) and child in cur.body:
            tests.append(ast.unparse(cur.test))
        elif (
            isinstance(cur, ast.If)
            and child in cur.orelse
            and not (len(cur.orelse) == 1 and isinstance(cur.orelse[0], ast.If))
        ):
            tests.append(f"not ({ast.unparse(cur.test)})")
        child, cur = cur, parents.get(cur)
    return " and ".join(reversed(tests)) or "always (fallthrough)"


def rows() -> list[tuple[str, str, str, str, str, int]]:
    source = ENGINE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    out: list[tuple[str, str, str, str, str, int]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "gate" for t in node.targets
        ):
            if isinstance(node.value, ast.Tuple) and isinstance(
                node.value.elts[0], ast.Constant
            ):
                rule, reason = node.value.elts
                out.append(
                    (
                        _text(rule),
                        "1 gate",
                        GATE_OUTCOMES.get(
                            _text(rule), "no recommendation (review required)"
                        ),
                        _conditions(parents, node),
                        _text(reason),
                        node.lineno,
                    )
                )
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "_Route" and isinstance(node.args[0], ast.Constant):
                route = node.args[1]
                outcome = (
                    "no recommendation (review required)"
                    if isinstance(route, ast.Constant) and route.value is None
                    else _text(route)
                )
                out.append(
                    (
                        _text(node.args[0]),
                        "3 route",
                        outcome,
                        _conditions(parents, node),
                        _text(node.args[3]),
                        node.lineno,
                    )
                )
            elif node.func.id == "_salvage_route" and isinstance(
                node.args[1], ast.Constant
            ):
                out.append(
                    (
                        _text(node.args[1]),
                        "3 route",
                        "liquidate if salvage > dispose_max_salvage, else dispose",
                        _conditions(parents, node),
                        _text(node.args[2]),
                        node.lineno,
                    )
                )
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "signoff"
            and isinstance(node.args[0], ast.Constant)
        ):
            code = str(node.args[0].value)
            out.append(
                (
                    code.split("_", 1)[0],
                    "sign-off",
                    "route stands; human sign-off required",
                    _conditions(parents, node),
                    code,
                    node.lineno,
                )
            )

    lines = source.splitlines()
    for lineno, line in enumerate(lines, 1):
        m = re.search(r"#\s*(R\d+[a-z]?)\s*$", line)
        if m and "review" in line:
            stmt = line.split("#")[0].strip()
            prev = lines[lineno - 2].strip() if lineno >= 2 else ""
            when = (
                prev.removeprefix("if ").rstrip(":")
                if prev.startswith("if ")
                else "always"
            )
            out.append(
                (
                    m.group(1),
                    "2 flag",
                    "review flag (route unchanged)",
                    when,
                    stmt,
                    lineno,
                )
            )
            continue
        if m and line.strip().startswith("if "):
            nxt = lines[lineno].strip() if lineno < len(lines) else ""
            out.append(
                (
                    m.group(1),
                    "2 flag",
                    "review flag (route unchanged)",
                    line.split("#")[0].strip().removeprefix("if ").rstrip(":"),
                    nxt,
                    lineno,
                )
            )

    step_order = {"1 gate": 0, "2 flag": 1, "3 route": 2, "sign-off": 3}
    return sorted(out, key=lambda r: (step_order[r[1]], r[5]))


def _cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def markdown() -> str:
    header = (
        "| Rule | Step | Outcome | When (engine condition) | Reason recorded | engine.py line |\n"
        "|---|---|---|---|---|---|\n"
    )
    body = ""
    for rule, step, outcome, when, reason, line in rows():
        reason_cell = f"`{_cell(reason)}`" if reason else ""
        body += f"| {rule} | {step} | {_cell(outcome)} | `{_cell(when)}` | {reason_cell} | {line} |\n"
    return header + body


if __name__ == "__main__":
    sys.stdout.write(markdown())
