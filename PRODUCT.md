# Org Lexicon

Org Lexicon helps a team turn explicit definitions in its documents into a reviewed, scoped glossary, then catch inconsistent usage. A proposed definition remains a candidate until a person approves it.

In the demo, “workspace” has one meaning in product documentation and another in infrastructure documentation. A document also uses the deprecated alias “team space.” The tool extracts definitions with their file and line, preserves the two scopes, and recommends the approved product term when checking a product guide. An explicitly marked term without an approved definition becomes a review finding.

The first release is a local CLI with candidate JSON, an approved glossary, Markdown/JSON exports, and a usage report. It recognizes a deliberately small explicit definition syntax. It does not infer an organization's full vocabulary from arbitrary prose or decide which competing definition is correct.

The useful distinction is provenance plus approval plus scope. A word list alone is insufficient, and an approved entry must not silently stay fresh after its source changes. Whole-file fingerprint changes ask for review even if the definition itself may be unchanged.

Validate on a small documentation set: measure useful terminology inconsistencies caught, rejected suggestions, and the effort to maintain a glossary. Do not equate a larger extracted glossary with better organizational understanding.
