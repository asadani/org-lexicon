"""Pure glossary operations and root-contained source inspection."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Any


class LexiconError(ValueError):
    """Expected invalid user data or source input."""


def _visible_lines(text: str):
    """Yield prose lines while respecting the opening fence's character and length."""
    opened = None
    for number, line in enumerate(text.splitlines(), 1):
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})(.*)$", line)
        if opened:
            if marker and marker.group(1)[0] == opened[0] and len(marker.group(1)) >= opened[1] and not marker.group(2).strip():
                opened = None
            continue
        if marker:
            opened = (marker.group(1)[0], len(marker.group(1)))
            continue
        yield number, line


def normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source(root: Path, rel: str) -> tuple[Path, bytes]:
    if not isinstance(rel, str) or not rel or Path(rel).is_absolute():
        raise LexiconError(f"source path must be a nonempty relative path: {rel!r}")
    root_real = root.resolve()
    candidate = (root_real / rel).resolve(strict=True)
    try:
        candidate.relative_to(root_real)
    except ValueError as exc:
        raise LexiconError(f"source path escapes root: {rel}") from exc
    if not candidate.is_file():
        raise LexiconError(f"source is not a file: {rel}")
    try:
        data = candidate.read_bytes()
        data.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise LexiconError(f"cannot read UTF-8 source {rel}: {exc}") from exc
    return candidate, data


def _relative_path(path: str) -> str:
    p = Path(path)
    if not path or p.is_absolute() or ".." in p.parts:
        raise LexiconError(f"path must stay within root: {path!r}")
    return p.as_posix()


def extract_candidates(root: Path, paths: list[str], scope: str) -> dict[str, Any]:
    if not isinstance(scope, str) or not scope.strip():
        raise LexiconError("scope must be a nonempty string")
    if not isinstance(paths, list) or not paths:
        raise LexiconError("at least one --file is required")
    output: list[dict[str, Any]] = []
    definition_re = re.compile(r"^\s*\*\*(.+?)\*\*\s*(?::|means)\s*(\S(?:.*\S)?)\s*$", re.I)
    for raw_path in paths:
        rel = _relative_path(raw_path)
        _, raw = _source(root, rel)
        text = raw.decode("utf-8")
        for line_no, line in _visible_lines(text):
            match = definition_re.match(line)
            if not match:
                continue
            term, definition = match.group(1).strip(), match.group(2).strip()
            if not term or not definition:
                continue
            identity = normalize(term)
            candidate_id = hashlib.sha256("\0".join((scope, identity, rel, str(line_no), definition)).encode()).hexdigest()[:20]
            output.append({"id": candidate_id, "term": term, "definition": definition, "scope": scope.strip(),
                           "aliases": [], "source": {"path": rel, "line_start": line_no, "line_end": line_no, "sha256": _sha(raw)},
                           "review_status": "proposed", "method": "explicit_definition_pattern"})
    output.sort(key=lambda c: (c["source"]["path"], c["source"]["line_start"], c["id"]))
    return {"schema_version": 1, "candidates": output}


def _validate_source(source: Any) -> None:
    if not isinstance(source, dict):
        raise LexiconError("source must be an object")
    path = source.get("path")
    _relative_path(path if isinstance(path, str) else "")
    for key in ("line_start", "line_end"):
        value = source.get(key)
        if type(value) is not int or value < 1:
            raise LexiconError(f"source.{key} must be a positive integer")
    if source["line_end"] < source["line_start"]:
        raise LexiconError("source.line_end must be at least line_start")
    digest = source.get("sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise LexiconError("source.sha256 must be a lowercase SHA-256 digest")


def _validate_entry(entry: Any, approved: bool) -> None:
    if not isinstance(entry, dict):
        raise LexiconError("each entry must be an object")
    for key in ("id", "term", "definition", "scope"):
        if not isinstance(entry.get(key), str) or not entry[key].strip():
            raise LexiconError(f"entry.{key} must be a nonempty string")
    if entry.get("review_status") != ("confirmed" if approved else "proposed"):
        raise LexiconError(f"entry {entry['id']} has invalid review_status")
    if entry.get("method") != "explicit_definition_pattern":
        raise LexiconError(f"entry {entry['id']} has unsupported method")
    _validate_source(entry.get("source"))
    aliases = entry.get("aliases")
    if not isinstance(aliases, list) or any(not isinstance(a, str) or not a.strip() for a in aliases):
        raise LexiconError(f"entry {entry['id']} aliases must be nonempty strings")
    seen = {normalize(entry["term"])}
    for alias in aliases:
        key = normalize(alias)
        if key in seen:
            raise LexiconError(f"entry {entry['id']} has duplicate alias or alias matching its term")
        seen.add(key)
    if approved:
        if not isinstance(entry.get("reviewer"), str) or not entry["reviewer"].strip():
            raise LexiconError(f"entry {entry['id']} reviewer must be nonempty")
        if not isinstance(entry.get("reviewed_at"), str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z", entry["reviewed_at"]):
            raise LexiconError(f"entry {entry['id']} reviewed_at must be UTC ISO 8601")
        try:
            datetime.fromisoformat(entry["reviewed_at"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise LexiconError(f"entry {entry['id']} reviewed_at is not a valid date/time") from exc


def validate_glossary(data: dict[str, Any]) -> None:
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise LexiconError("glossary schema_version must be integer 1")
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise LexiconError("glossary entries must be an array")
    ids: set[str] = set()
    identities: dict[tuple[str, str], str] = {}
    for entry in entries:
        _validate_entry(entry, True)
        if entry["id"] in ids:
            raise LexiconError(f"duplicate glossary entry id: {entry['id']}")
        ids.add(entry["id"])
        scope = entry["scope"]
        for term in [entry["term"], *entry["aliases"]]:
            key = (scope, normalize(term))
            if key in identities and identities[key] != entry["id"]:
                raise LexiconError(f"term or alias collision in scope {scope!r}: {term}")
            identities[key] = entry["id"]


def _validate_candidates(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise LexiconError("candidate schema_version must be integer 1")
    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        raise LexiconError("candidates must be an array")
    ids: set[str] = set()
    for candidate in candidates:
        _validate_entry(candidate, False)
        if candidate["id"] in ids:
            raise LexiconError(f"duplicate candidate id: {candidate['id']}")
        ids.add(candidate["id"])
    return candidates


def approve_candidate(candidates: dict[str, Any], glossary: dict[str, Any], candidate_id: str,
                      reviewer: str, reviewed_at: str) -> dict[str, Any]:
    selected = next((c for c in _validate_candidates(candidates) if c["id"] == candidate_id), None)
    if selected is None:
        raise LexiconError(f"unknown candidate id: {candidate_id}")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise LexiconError("reviewer must be nonempty")
    candidate = json.loads(json.dumps(selected))
    current = {"schema_version": 1, "entries": []} if glossary is None else json.loads(json.dumps(glossary))
    validate_glossary(current)
    for prior in current["entries"]:
        if prior["id"] == candidate_id:
            metadata = {"review_status", "reviewer", "reviewed_at"}
            old_content = {k: v for k, v in prior.items() if k not in metadata}
            new_content = {k: v for k, v in candidate.items() if k not in metadata}
            if old_content != new_content:
                raise LexiconError("candidate ID is already approved with different content; use a new candidate ID or explicitly review the glossary edit")
            return current
    candidate.update(review_status="confirmed", reviewer=reviewer.strip(), reviewed_at=reviewed_at)
    _validate_entry(candidate, True)
    for prior in current["entries"]:
        if prior["scope"] != candidate["scope"]:
            continue
        if normalize(prior["term"]) == normalize(candidate["term"]):
            raise LexiconError(f"canonical term already approved in scope {candidate['scope']!r}: {candidate['term']}")
        prior_names = {normalize(prior["term"]), *(normalize(x) for x in prior["aliases"])}
        new_names = {normalize(candidate["term"]), *(normalize(x) for x in candidate["aliases"])}
        overlap = prior_names & new_names
        if overlap:
            raise LexiconError(f"term or alias collision in scope {candidate['scope']!r}: {sorted(overlap)[0]}")
    current["entries"].append(candidate)
    validate_glossary(current)
    return current


def effective_entries(glossary: dict[str, Any], scope: str) -> list[dict[str, Any]]:
    validate_glossary(glossary)
    if not isinstance(scope, str) or not scope.strip():
        raise LexiconError("scope must be a nonempty string")
    scoped = [e for e in glossary["entries"] if e["scope"] == scope.strip()]
    overrides = {normalize(e["term"]) for e in scoped}
    result = [e for e in glossary["entries"] if e["scope"] == "global" and normalize(e["term"]) not in overrides]
    result.extend(scoped)
    result.sort(key=lambda e: (normalize(e["term"]), e["scope"], e["id"]))
    return result


def check_documents(glossary: dict[str, Any], root: Path, paths: list[str], scope: str) -> dict[str, Any]:
    entries = effective_entries(glossary, scope)
    findings: list[dict[str, Any]] = []
    aliases: dict[str, list[dict[str, Any]]] = {}
    # Same alias can arise in different effective scopes; preserve ambiguity visibly.
    for entry in entries:
        for spelling in entry["aliases"]:
            aliases.setdefault(normalize(spelling), []).append(entry)
    for entry in entries:
        try:
            _, raw = _source(root, entry["source"]["path"])
            if entry["source"]["line_end"] > len(raw.decode("utf-8").splitlines()):
                findings.append(_finding("invalid_definition_source_range", entry["source"]["path"], entry["source"]["line_start"], entry["id"], "Approved definition cites lines outside its source; review the reference."))
            if _sha(raw) != entry["source"]["sha256"]:
                findings.append(_finding("stale_definition_source", entry["source"]["path"], entry["source"]["line_start"], entry["id"], "Approved definition source has changed; review the glossary entry."))
        except (LexiconError, OSError):
            findings.append(_finding("missing_definition_source", entry["source"]["path"], entry["source"]["line_start"], entry["id"], "Approved definition source is missing or unreadable."))
    # Check cross-entry collisions in the effective set, including canonical/alias combinations.
    names: dict[str, set[str]] = {}
    for entry in entries:
        for spelling in [entry["term"], *entry["aliases"]]:
            names.setdefault(normalize(spelling), set()).add(entry["id"])
    ambiguous = {k for k, ids in names.items() if len(ids) > 1}
    for key in sorted(ambiguous):
        findings.append(_finding("ambiguous_lexicon", "", 1, key, f"Effective glossary has an ambiguous term or alias: {key}"))
    for raw_path in paths:
        rel = _relative_path(raw_path)
        _, raw = _source(root, rel)
        text = raw.decode("utf-8")
        for line_no, line in _visible_lines(text):
            markers = list(re.finditer(r"\[\[term:([^\]]+)\]\]", line, re.I))
            for marker in markers:
                name = marker.group(1).strip()
                key = normalize(name)
                if key in ambiguous:
                    continue
                matches = [e for e in entries if key == normalize(e["term"]) or any(key == normalize(a) for a in e["aliases"])]
                kind = "undefined_marked_term" if not matches else "discouraged_alias" if any(key in {normalize(a) for a in e["aliases"]} for e in matches) else None
                if kind:
                    ent = matches[0] if matches else None
                    findings.append(_finding(kind, rel, line_no, (ent["id"] if ent else key), f"Explicitly marked term {name!r} is {'not in the effective glossary' if not ent else 'a discouraged alias'}.", entry_id=ent["id"] if ent else None, suggestion=ent["term"] if ent else None))
            matches: list[tuple[int, int, str, dict[str, Any]]] = []
            for alias, owners in aliases.items():
                if alias in ambiguous:
                    continue
                for owner in owners:
                    for display in owner["aliases"]:
                        if normalize(display) != alias:
                            continue
                        pat = re.compile(r"(?<!\w)" + re.escape(display) + r"(?!\w)", re.I)
                        matches.extend((m.start(), m.end(), m.group(), owner) for m in pat.finditer(line)
                                       if not any(m.start() < marker.end() and m.end() > marker.start() for marker in markers))
            matches.sort(key=lambda item: (item[0], -(item[1]-item[0]), item[3]["id"]))
            chosen: list[tuple[int, int, str, dict[str, Any]]] = []
            end = -1
            for match in matches:
                if match[0] >= end:
                    chosen.append(match)
                    end = match[1]
            for start, stop, literal, owner in chosen:
                findings.append(_finding("discouraged_alias", rel, line_no, owner["id"] + ":" + str(start), f"Use preferred term {owner['term']!r} instead of {literal!r}.", entry_id=owner["id"], suggestion=owner["term"]))
    findings.sort(key=lambda f: (f.get("source", {}).get("path", ""), f.get("source", {}).get("line_start", 0), f["kind"], f["id"]))
    return {"schema_version": 1, "scope": scope, "findings": findings, "limitations": ["Structural terminology checks; arbitrary undefined terms are not detected."]}


def _finding(kind: str, path: str, line: int, subject: str, message: str, entry_id: str | None = None, suggestion: str | None = None) -> dict[str, Any]:
    fid = hashlib.sha256(f"{kind}\0{path}\0{line}\0{subject}".encode()).hexdigest()[:20]
    item: dict[str, Any] = {"id": fid, "kind": kind, "message": message}
    if path:
        item["source"] = {"path": path, "line_start": line, "line_end": line}
    if entry_id:
        item["entry_id"] = entry_id
    if suggestion:
        item["suggestion"] = suggestion
    return item


def export_markdown(glossary: dict[str, Any], scope: str) -> str:
    entries = effective_entries(glossary, scope)
    def cell(value: str) -> str:
        return value.replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")
    rows = [f"# Approved glossary: {cell(scope)}", "", "Effective entries include this scope and global fallback. Original scopes are shown.", "", "| Term | Definition | Aliases (discouraged) | Scope | Provenance |", "| --- | --- | --- | --- | --- |"]
    for e in entries:
        src = e["source"]
        provenance = f"{cell(src['path'])}:{src['line_start']} ({src['sha256'][:12]})"
        rows.append("| " + " | ".join((cell(e["term"]), cell(e["definition"]), cell(", ".join(e["aliases"])), cell(e["scope"]), provenance)) + " |")
    return "\n".join(rows) + "\n"


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise

