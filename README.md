# Org Lexicon

Org Lexicon extracts explicit definitions as review candidates, keeps approved terms separate by scope, and locates discouraged names in selected Markdown files. Candidates are never silently promoted.

![Org Lexicon logo](assets/logo.svg)

## Quickstart

Run from this directory with Python 3.11 or newer. The following uses only the included fixtures and writes generated files to a temporary directory:

```sh
set -eu
DEMO_DIR="$(mktemp -d)"
trap 'rm -rf "$DEMO_DIR"' EXIT
python -m org_lexicon extract --root fixtures --scope product --file product.md --out "$DEMO_DIR/candidates.json"
CANDIDATE_ID="$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["candidates"][0]["id"])' "$DEMO_DIR/candidates.json")"
python -c 'import json,sys; p=sys.argv[1]; d=json.load(open(p)); d["candidates"][0]["aliases"]=["team space"]; open(p,"w").write(json.dumps(d,indent=2)+"\n")' "$DEMO_DIR/candidates.json"
python -m org_lexicon approve "$DEMO_DIR/candidates.json" --id "$CANDIDATE_ID" --reviewer "Demo editor" --reviewed-at 2026-10-22T01:00:00Z --glossary "$DEMO_DIR/glossary.json"
python -m org_lexicon export "$DEMO_DIR/glossary.json" --scope product --format markdown --out "$DEMO_DIR/glossary.md"
if python -m org_lexicon check "$DEMO_DIR/glossary.json" --root fixtures --scope product --file guide.md --out "$DEMO_DIR/findings.json"; then
  echo "Expected the guide fixture to produce findings" >&2; exit 1
else
  code=$?
  test "$code" -eq 1
fi
python -c 'import json,sys; print("Findings:", ", ".join(f["kind"] for f in json.load(open(sys.argv[1]))["findings"]))' "$DEMO_DIR/findings.json"
```

The last command should list a discouraged alias and an explicitly marked undefined term. The infrastructure fixture defines `Workspace` independently; extract it with `--scope infrastructure` to preserve that separate meaning. To check multiple chosen files, repeat `--file` for each one.

Expected exits are `0` for successful extraction, approval, export, or a clean check; `1` when a check completes with findings; and `2` for invalid JSON/data, an unreadable file, or an operational error. JSON reports go to stdout unless `--out` is supplied. Run `python -m org_lexicon --help` for command details.

## What the checks mean

Extraction recognizes only full-line `**Term**: Definition` and `**Term** means Definition` forms outside fenced code blocks. Identity compares case-insensitively after whitespace folding while retaining the original spelling. Approved aliases mean “discouraged spelling; prefer this canonical name.” They are not semantic synonyms.

The checker locates aliases in normal text using case-insensitive, word-bounded matching and checks explicit `[[term:Some phrase]]` markers. It does not flag every unfamiliar word. It checks each effective glossary source fingerprint and reports changed or missing files; it does not revoke approval or refresh fingerprints. Paths are resolved inside `--root`, including symlinks.

This is a structural terminology check. It does not infer an organization's full vocabulary, decide between competing definitions, infer synonyms, edit source documents, or establish that a definition is correct. A clean result means only that no configured terminology findings were observed in the selected files.

## Formats and tests

See [the JSON format reference](docs/SCHEMA.md). To run the standard-library test suite:

```sh
python -m unittest discover -s tests -v
```

## Data integrity

Report/export paths cannot overwrite checked files, glossary inputs, or referenced definition sources. Exact reapproval is a no-op; a candidate with an already approved ID and changed content is rejected. Checks report invalid cited source ranges, and ambiguous effective aliases never select an arbitrary replacement.

See [verification coverage](docs/VERIFICATION.md) and [the design plan](docs/PLAN.md) for tested behavior and remaining limits.
