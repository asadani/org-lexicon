import json
import tempfile
import unittest
from pathlib import Path

from org_lexicon.core import (LexiconError, approve_candidate, check_documents,
                              effective_entries, extract_candidates, validate_glossary)


class OrgLexiconTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "source.md").write_text("**Workspace**: Product work area.\n", encoding="utf-8")
        self.candidates = extract_candidates(self.root, ["source.md"], "product")
        self.candidate = self.candidates["candidates"][0]

    def tearDown(self):
        self.temp.cleanup()

    def approve(self, candidate=None, glossary=None):
        c = self.candidates if candidate is None else {"schema_version": 1, "candidates": [candidate]}
        return approve_candidate(c, glossary, candidate["id"] if candidate else self.candidate["id"], "Reviewer", "2026-10-22T01:00:00Z")

    def test_extract_provenance_and_fence_exclusion_repeatable_id(self):
        (self.root / "more.md").write_text("````\n**Bad**: hidden\n````\n**Good** means visible definition.\n", encoding="utf-8")
        first = extract_candidates(self.root, ["more.md"], "product")
        second = extract_candidates(self.root, ["more.md"], "product")
        self.assertEqual(first, second)
        self.assertEqual([x["term"] for x in first["candidates"]], ["Good"])
        self.assertEqual(first["candidates"][0]["source"]["line_start"], 4)

    def test_approval_scopes_and_idempotence(self):
        glossary = self.approve()
        same = approve_candidate(self.candidates, glossary, self.candidate["id"], "Other", "2027-01-01T00:00:00Z")
        self.assertEqual(glossary, same)
        infra = dict(self.candidate, id="different", scope="infrastructure")
        both = self.approve(infra, glossary)
        self.assertEqual({e["scope"] for e in effective_entries(both, "infrastructure")}, {"infrastructure"})
        self.assertEqual({e["scope"] for e in effective_entries(both, "product")}, {"product"})

    def test_alias_check_scope_freshness_and_no_mutation(self):
        candidate = dict(self.candidate, aliases=["team space"])
        glossary = self.approve(candidate)
        (self.root / "guide.md").write_text("team space but not team spacesuit; [[term:unknown]].\n", encoding="utf-8")
        before = json.dumps(glossary, sort_keys=True)
        report = check_documents(glossary, self.root, ["guide.md"], "product")
        self.assertEqual({f["kind"] for f in report["findings"]}, {"discouraged_alias", "undefined_marked_term"})
        self.assertEqual(sum(f["kind"] == "discouraged_alias" for f in report["findings"]), 1)
        self.assertEqual(json.dumps(glossary, sort_keys=True), before)
        (self.root / "source.md").write_text("changed\n", encoding="utf-8")
        stale = check_documents(glossary, self.root, [], "product")
        self.assertIn("stale_definition_source", {f["kind"] for f in stale["findings"]})
        (self.root / "source.md").unlink()
        missing = check_documents(glossary, self.root, [], "product")
        self.assertIn("missing_definition_source", {f["kind"] for f in missing["findings"]})

    def test_global_override_and_collision_ambiguity(self):
        global_entry = dict(self.candidate, id="g", scope="global", aliases=["shared"])
        specific = dict(self.candidate, id="s", term="Other", scope="product", aliases=["shared"])
        glossary = {"schema_version": 1, "entries": []}
        for c in (global_entry, specific):
            glossary = self.approve(c, glossary)
        eff = effective_entries(glossary, "product")
        self.assertEqual({e["id"] for e in eff}, {"g", "s"})
        # Cross-scope aliases can collide in the effective view; never suggest arbitrarily.
        report = check_documents(glossary, self.root, [], "product")
        self.assertIn("ambiguous_lexicon", {f["kind"] for f in report["findings"]})

    def test_escape_and_symlink_refs_rejected(self):
        outside = self.root.parent / (self.root.name + "-outside")
        outside.write_text("**Escaped**: no\n", encoding="utf-8")
        try:
            (self.root / "link.md").symlink_to(outside)
            with self.assertRaises(LexiconError):
                extract_candidates(self.root, ["../outside.md"], "x")
            with self.assertRaises(LexiconError):
                extract_candidates(self.root, ["link.md"], "x")
        finally:
            outside.unlink(missing_ok=True)

    def test_schema_rejects_bool_float_and_bad_enum_without_mutation(self):
        for version in (True, 1.0, "1"):
            with self.assertRaises(LexiconError):
                validate_glossary({"schema_version": version, "entries": []})
        original = self.approve()
        broken = json.loads(json.dumps(original))
        broken["entries"][0]["source"]["line_start"] = True
        with self.assertRaises(LexiconError):
            approve_candidate(self.candidates, broken, self.candidate["id"], "Reviewer", "2026-10-22T01:00:00Z")
        self.assertEqual(len(original["entries"]), 1)

    def test_reject_duplicate_scope_term_and_alias_collision(self):
        glossary = self.approve()
        duplicate = dict(self.candidate, id="second")
        with self.assertRaises(LexiconError):
            self.approve(duplicate, glossary)
        alias = dict(self.candidate, id="alias", term="Different", aliases=["workspace"])
        with self.assertRaises(LexiconError):
            self.approve(alias, glossary)


if __name__ == "__main__":
    unittest.main()
