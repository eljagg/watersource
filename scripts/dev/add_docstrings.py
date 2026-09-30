"""One-off helper used in Sprint 1 to insert/replace docstrings from a mapping (kept for reference).

Usage: ``python scripts/dev/add_docstrings.py mapping.json``. Keys are
``"<file>": {"__module__": "...", "Class": "...", "Class.method": "..."}``.
Existing docstrings are replaced; missing ones are inserted after the def line.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _format(doc: str, indent: str) -> list[str]:
    doc = doc.strip()
    if "\n" not in doc:
        return [f'{indent}"""{doc}"""']
    lines = doc.split("\n")
    out = [f'{indent}"""{lines[0]}']
    out += [(indent + ln) if ln.strip() else "" for ln in lines[1:]]
    out.append(f'{indent}"""')
    return out


def apply(path: Path, mapping: dict[str, str]) -> int:
    """Insert or replace docstrings in ``path``; returns the number of edits."""
    src = path.read_text().split("\n")
    tree = ast.parse("\n".join(src))
    edits: list[tuple[int, int, list[str]]] = []  # (start_line_idx, end_line_idx_exclusive, new_lines)

    def handle(node, qual):
        first = node.body[0] if node.body else None
        is_doc = isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) and isinstance(first.value.value, str)
        doc_node = first if is_doc else None
        text = mapping.get(qual)
        if text is None:
            return
        if isinstance(node, ast.Module):
            indent = ""
            if doc_node:
                edits.append((doc_node.lineno - 1, doc_node.end_lineno, _format(text, indent)))
            else:
                edits.append((0, 0, _format(text, indent)))
            return
        body_first = node.body[0]
        indent = _indent_of(src[body_first.lineno - 1])
        if doc_node:
            edits.append((doc_node.lineno - 1, doc_node.end_lineno, _format(text, indent)))
        else:
            # insert before the first body statement (handles multi-line signatures)
            edits.append((body_first.lineno - 1, body_first.lineno - 1, _format(text, indent)))

    def walk(n, q=""):
        for c in ast.iter_child_nodes(n):
            if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{q}.{c.name}" if q else c.name
                handle(c, name)
                walk(c, name)
            else:
                walk(c, q)

    handle(tree, "__module__")
    walk(tree)
    for start, end, new in sorted(edits, key=lambda e: e[0], reverse=True):
        src[start:end] = new
    path.write_text("\n".join(src))
    return len(edits)


if __name__ == "__main__":
    spec = json.loads(Path(sys.argv[1]).read_text())
    total = 0
    for file, mapping in spec.items():
        total += apply(Path(file), mapping)
    print(f"{total} docstrings written")
