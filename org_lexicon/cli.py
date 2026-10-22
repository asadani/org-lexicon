from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .core import (LexiconError, approve_candidate, check_documents, effective_entries,
                   export_markdown, extract_candidates, validate_glossary, write_json_atomic)


def _protect_inputs(output, sources):
    if output is None:
        return
    destination = Path(output).resolve()
    for source in sources:
        if source is not None and destination == Path(source).resolve():
            raise LexiconError("output must not overwrite an input file; choose a separate report path")


def _read_json(path: str, *, optional: bool = False) -> Any:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        if optional:
            return None
        raise LexiconError(f"file not found: {path}")
    except (OSError, UnicodeDecodeError) as exc:
        raise LexiconError(f"cannot read {path}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LexiconError(f"invalid JSON in {path} at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc


def _write(path: str | None, value: Any, is_json: bool = True) -> None:
    content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n" if is_json else value
    if path:
        target = Path(path)
        if is_json:
            write_json_atomic(target, value)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
    else:
        sys.stdout.write(content)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="org-lexicon", description="Review explicit definitions and check scoped terminology.")
    parser.add_argument("--version", action="version", version=f"org-lexicon {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("extract", help="extract explicit definition candidates")
    p.add_argument("--root", default=".")
    p.add_argument("--scope", required=True)
    p.add_argument("--file", action="append", required=True)
    p.add_argument("--out")
    p = commands.add_parser("approve", help="approve one candidate into a glossary")
    p.add_argument("candidates")
    p.add_argument("--id", required=True)
    p.add_argument("--reviewer", required=True)
    p.add_argument("--reviewed-at", help="UTC timestamp; defaults to current UTC time")
    p.add_argument("--glossary", required=True)
    p = commands.add_parser("export", help="export approved entries for a scope")
    p.add_argument("glossary")
    p.add_argument("--scope", required=True)
    p.add_argument("--format", choices=("json", "markdown"), default="json")
    p.add_argument("--out")
    p = commands.add_parser("check", help="check explicit files against an approved glossary")
    p.add_argument("glossary")
    p.add_argument("--root", default=".")
    p.add_argument("--scope", required=True)
    p.add_argument("--file", action="append", required=True)
    p.add_argument("--out")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "extract":
            _protect_inputs(args.out, [Path(args.root) / name for name in args.file])
            result = extract_candidates(Path(args.root), args.file, args.scope)
            _write(args.out, result)
            return 0
        if args.command == "approve":
            _protect_inputs(args.glossary, [args.candidates])
            candidates = _read_json(args.candidates)
            target = Path(args.glossary)
            glossary = _read_json(args.glossary, optional=True)
            if args.reviewed_at is None:
                from datetime import datetime, timezone
                reviewed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            else:
                reviewed_at = args.reviewed_at
            result = approve_candidate(candidates, glossary, args.id, args.reviewer, reviewed_at)
            # A fully validated result is computed before the atomic replacement.
            validate_glossary(result)
            write_json_atomic(target, result)
            return 0
        if args.command == "export":
            _protect_inputs(args.out, [args.glossary])
            glossary = _read_json(args.glossary)
            validate_glossary(glossary)
            if args.format == "markdown":
                _write(args.out, export_markdown(glossary, args.scope), is_json=False)
            else:
                _write(args.out, {"schema_version": 1, "scope": args.scope, "entries": effective_entries(glossary, args.scope)})
            return 0
        if args.command == "check":
            glossary = _read_json(args.glossary)
            validate_glossary(glossary)
            _protect_inputs(args.out, [args.glossary, *[Path(args.root) / name for name in args.file],
                *[Path(args.root) / entry["source"]["path"] for entry in effective_entries(glossary, args.scope)]])
            report = check_documents(glossary, Path(args.root), args.file, args.scope)
            _write(args.out, report)
            return 1 if report["findings"] else 0
        parser.error("unknown command")
    except (LexiconError, OSError, ValueError) as exc:
        print(f"org-lexicon: error: {exc}", file=sys.stderr)
        return 2
    return 2

