# Org Lexicon v0.1 implementation plan

## Required workflow and CLI

Extract explicit definitions from Markdown, approve selected candidates, export a glossary, and check document usage in one scope.

```sh
python -m org_lexicon extract --root fixtures --scope product --file product.md --out candidates.json
python -m org_lexicon approve candidates.json --id <candidate-id> --reviewer "Demo editor" --glossary glossary.json
python -m org_lexicon export glossary.json --scope product --format markdown --out glossary.md
python -m org_lexicon check glossary.json --root fixtures --scope product --file guide.md --out findings.json
```

`--file` is repeatable; explicit files only, no implicit recursive scan. `approve` creates a new glossary if absent and otherwise atomically appends a selected candidate after full validation. It never approves all candidates implicitly. `export --format json` emits the effective approved glossary. `check` returns 1 for usage/definition/source findings, 0 clean, 2 invalid input. Extraction reports conflicts as candidates rather than deciding which definition is correct.

## Extraction and formats

Recognize only whole-line definitions `**Term**: Definition text` and `**Term** means Definition text`. Ignore fenced code blocks. Case-insensitive matching is for identity only; preserve original display spelling. This is structural extraction, labeled `method: explicit_definition_pattern`; other prose is outside coverage. Normalize identity by Unicode casefold plus collapsed whitespace. Each candidate has `{id,term,definition,scope,aliases:[],source:{path,line_start,line_end,sha256},review_status:"proposed",method}`. IDs are a stable SHA-256-derived prefix of scope, normalized term, relative path, line number, and definition (at least 16 hex chars). Candidate artifact: `{schema_version:1,candidates:[...]}` sorted by path and line.

An approved glossary is `{schema_version:1,entries:[...]}`. Entries retain candidate fields and add `review_status:"confirmed"`, `reviewer`, and `reviewed_at`. Users may edit candidate `aliases` before approval; aliases are nonempty unique strings distinct from the canonical term under normalization. All aliases mean “discouraged spelling/name; prefer canonical term,” not semantic synonyms. The help text must explain this limited meaning.

Approval rejects a second approved canonical term with the same normalized identity in the same scope. It also rejects collisions between any canonical term/alias and another entry's term/alias within that scope. Reapproving the exact same candidate is an idempotent no-op and does not change its original reviewer/time. Different scopes can define the same term. Editing a glossary is a manual JSON operation in v0.1; no merge/replace workflow is required.

Scopes are nonempty strings; `global` is the fallback scope. For a requested scope, include that scope and global. A scoped canonical term overrides the global entry with the same canonical identity; otherwise retain global entries. If the resulting set has cross-entry alias collisions, report an ambiguous-lexicon finding and do not make an arbitrary replacement suggestion for that alias. Export discloses requested and original entry scopes.

## Checking and core API

Find aliases in ordinary document text using escaped case-insensitive regex with non-word boundaries; prefer longest matching alias and do not double-count overlapping occurrences. Findings provide file, line, literal matched text, canonical suggestion, glossary entry ID, and scope. Ignore fenced code blocks. Check explicit `[[term:Some phrase]]` markers against the effective canonical terms or aliases: unknown is `undefined_marked_term`; an alias is `discouraged_alias`. Do not label every unfamiliar word undefined.

Check source fingerprints for all effective entries independently of usage: changed source is `stale_definition_source`; missing/unreadable source is `missing_definition_source`. The glossary remains approved history, but the report makes maintenance risk visible. Source status must not automatically revoke approval or refresh hashes. Input source paths are root-relative and checked against the supplied root.

- `extract_candidates(root: Path, paths: list[str], scope: str) -> dict`
- `validate_glossary(data: dict) -> None`
- `approve_candidate(candidates: dict, glossary: dict, candidate_id: str, reviewer: str, reviewed_at: str) -> dict`
- `effective_entries(glossary: dict, scope: str) -> list[dict]`
- `check_documents(glossary: dict, root: Path, paths: list[str], scope: str) -> dict`
- `export_markdown(glossary: dict, scope: str) -> str`

Reports have `{schema_version:1,scope,findings:[{id,kind,message,source?,entry_id?,suggestion?}]}`. Finding IDs derive from kind plus location plus affected entry/term; stable ordering is path, line, kind. Display “structural terminology checks; arbitrary undefined terms are not detected.”

## Fixtures and acceptance tests

1. Product and infrastructure docs define Workspace differently; extraction retains both with exact provenance and scopes. Fenced examples do not create candidates.
2. Approve a product candidate and an infrastructure candidate; one does not override the other. A proposed entry is never exported as approved.
3. A guide's “team space” alias yields one located suggestion; “team spacesuit” must not match. Unknown explicit marker yields undefined finding. Ordinary unrelated words do not.
4. Global fallback works; same canonical term in the requested scope overrides global. An effective alias collision produces ambiguity without an arbitrary suggestion.
5. Source change or deletion produces stale/missing source findings; check never rewrites stored fingerprints or approval state.
6. Duplicate same-scope canonical terms, alias collisions, broken source ranges, empty reviewers, invalid JSON, and escaping paths fail without corrupting the glossary. Exact reapproval is idempotent.
7. End-to-end CLI extraction/approval/export/check runs from a temporary fixture copy. JSON exports preserve provenance; Markdown escapes table separators/newlines.

## Boundaries and milestone

Required: extraction, approval, scope resolution, source freshness, usage checks, exports, tests. Deferred: embeddings, semantic synonyms, general entity extraction, translation, browser extensions, collaborative approvals, automatic source rewriting. The tool suggests consistent names but never edits the checked document.

Build identity/scope validation first, then extraction/approval, then checker/export. Done means a realistic guide shows both a discouraged alias and an undefined explicitly marked term while two legitimate scoped definitions coexist.
