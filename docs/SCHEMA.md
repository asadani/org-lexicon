# Org Lexicon JSON formats

All artifacts use UTF-8 JSON and `schema_version: 1`. Generated JSON is stable and sorted by key; arrays preserve their documented order. Paths are relative to the CLI `--root`. `source.sha256` fingerprints original file bytes, so any source edit marks an approved definition stale.

## Candidate artifact

`extract` emits `{ "schema_version": 1, "candidates": [...] }`. A candidate contains `id`, `term`, `definition`, `scope`, `aliases`, `source`, `review_status: "proposed"`, and `method: "explicit_definition_pattern"`. IDs are deterministic for identical scope, source, line, term, and definition. The source object has `path`, positive inclusive `line_start` and `line_end`, and lowercase `sha256`.

Aliases are optional spelling/name variants that should be replaced with the canonical term. They do not represent semantic synonyms. Before approval, a reviewer may edit a candidate's aliases in the JSON.

## Approved glossary

`{ "schema_version": 1, "entries": [...] }` contains approved candidate records with `review_status: "confirmed"`, a nonempty `reviewer`, and `reviewed_at` in UTC ISO 8601 form. Each scope has unique canonical terms and no term/alias collisions. Reapproving an existing candidate ID is an idempotent no-op.

When checking or exporting a scope, entries from that scope and `global` are effective. A scoped canonical term overrides its global canonical counterpart. A conflicting effective alias is reported as ambiguous, without a replacement recommendation.

## Findings

`check` emits `{ "schema_version": 1, "scope": "...", "findings": [...], "limitations": [...] }`. A finding has a deterministic `id`, `kind`, and `message`, and may include a located `source`, `entry_id`, or canonical `suggestion`. Kinds include `discouraged_alias`, `undefined_marked_term`, `stale_definition_source`, `missing_definition_source`, and `ambiguous_lexicon`.
