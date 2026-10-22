import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_help_version_and_end_to_end_exit(self):
        help_result = subprocess.run([sys.executable, "-m", "org_lexicon", "--help"], cwd=REPO, text=True, capture_output=True)
        version_result = subprocess.run([sys.executable, "-m", "org_lexicon", "--version"], cwd=REPO, text=True, capture_output=True)
        self.assertEqual(help_result.returncode, 0)
        self.assertIn("extract", help_result.stdout)
        self.assertEqual(version_result.stdout.strip(), "org-lexicon 0.1.0")
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            for name in ("product.md", "guide.md"):
                (temp_path / name).write_bytes((REPO / "fixtures" / name).read_bytes())
            candidates = temp_path / "candidates.json"
            r = subprocess.run([sys.executable, "-m", "org_lexicon", "extract", "--root", str(temp_path), "--scope", "product", "--file", "product.md", "--out", str(candidates)], cwd=REPO, text=True, capture_output=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            cid = json.loads(candidates.read_text())["candidates"][0]["id"]
            candidate_data = json.loads(candidates.read_text())
            candidate_data["candidates"][0]["aliases"] = ["team space"]
            candidates.write_text(json.dumps(candidate_data), encoding="utf-8")
            glossary = temp_path / "glossary.json"
            r = subprocess.run([sys.executable, "-m", "org_lexicon", "approve", str(candidates), "--id", cid, "--reviewer", "Demo", "--reviewed-at", "2026-10-22T01:00:00Z", "--glossary", str(glossary)], cwd=REPO, text=True, capture_output=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            r = subprocess.run([sys.executable, "-m", "org_lexicon", "check", str(glossary), "--root", str(temp_path), "--scope", "product", "--file", "guide.md"], cwd=REPO, text=True, capture_output=True)
            self.assertEqual(r.returncode, 1)
            report = json.loads(r.stdout)
            self.assertTrue({"discouraged_alias", "undefined_marked_term"} <= {f["kind"] for f in report["findings"]})
            malformed = temp_path / "invalid.json"
            malformed.write_text("{", encoding="utf-8")
            r = subprocess.run([sys.executable, "-m", "org_lexicon", "export", str(malformed), "--scope", "product"], cwd=REPO, text=True, capture_output=True)
            self.assertEqual(r.returncode, 2)
            self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
