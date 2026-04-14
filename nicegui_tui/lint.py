"""Static AST checker: flag ui.* calls and classes() values outside the supported subset.

Usage: nicegui-tui check path/to/app.py
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

SUPPORTED_ELEMENTS = {
    "label", "markdown", "button", "input", "textarea", "checkbox", "switch",
    "radio", "select", "row", "column", "card", "separator", "notify", "dialog",
}

# Framework-level APIs that are always allowed (not widgets).
FRAMEWORK_APIS = {
    "page", "run", "run_with", "timer", "add_css", "add_head_html",
    "add_body_html", "add_sass", "add_scss", "dark_mode", "colors",
    "navigate", "on", "context", "query", "refreshable", "state",
    "update", "keyboard", "clipboard",
}

KNOWN_CLASSES = {
    "tcss-border", "tcss-padded", "tcss-muted", "tcss-primary",
    "tcss-danger", "tcss-success", "tcss-warning", "tcss-bold",
    "tui-hide", "tui-only",
}


class Finding:
    __slots__ = ("path", "line", "col", "kind", "detail")

    def __init__(self, path: str, line: int, col: int, kind: str, detail: str) -> None:
        self.path = path
        self.line = line
        self.col = col
        self.kind = kind
        self.detail = detail

    def format(self) -> str:
        return f"{self.path}:{self.line}:{self.col}: {self.kind}: {self.detail}"


def _extract_string_literals(node: ast.AST) -> list[str]:
    out: list[str] = []
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        out.append(node.value)
    elif isinstance(node, ast.JoinedStr):
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                out.append(v.value)
    return out


def check_file(path: Path) -> list[Finding]:
    source = path.read_text()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        return [Finding(str(path), e.lineno or 0, e.offset or 0, "SYNTAX", str(e))]
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if (func.value.id == "ui"
                    and func.attr not in SUPPORTED_ELEMENTS
                    and func.attr not in FRAMEWORK_APIS):
                if func.attr.islower() and not func.attr.startswith("_"):
                    findings.append(Finding(
                        str(path), node.lineno, node.col_offset,
                        "UNSUPPORTED_ELEMENT", f"ui.{func.attr} not in subset",
                    ))
            if func.attr == "classes":
                for arg in node.args:
                    for s in _extract_string_literals(arg):
                        for cls in s.split():
                            if cls.startswith(("tcss-", "tui-")) and cls not in KNOWN_CLASSES:
                                findings.append(Finding(
                                    str(path), node.lineno, node.col_offset,
                                    "UNKNOWN_CLASS", f"class {cls!r} not recognized",
                                ))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nicegui-tui")
    sub = parser.add_subparsers(dest="cmd", required=True)
    check = sub.add_parser("check", help="Static-check a NiceGUI app for TUI compat")
    check.add_argument("path", type=Path)
    args = parser.parse_args(argv)

    if args.cmd == "check":
        if not args.path.exists():
            print(f"no such file: {args.path}", file=sys.stderr)
            return 2
        paths = [args.path] if args.path.is_file() else list(args.path.rglob("*.py"))
        total: list[Finding] = []
        for p in paths:
            total.extend(check_file(p))
        if not total:
            print("OK: no TUI-compat issues found")
            return 0
        for f in total:
            print(f.format())
        print(f"\n{len(total)} finding(s)")
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
