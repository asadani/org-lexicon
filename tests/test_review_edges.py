"""Independent review regressions for scoped suggestions."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from org_lexicon.core import check_documents, validate_glossary, LexiconError

class ScopedReviewTests(unittest.TestCase):
    def fixture(self, root):
        (root/'source.md').write_text('Definition evidence.\n')
        digest=hashlib.sha256((root/'source.md').read_bytes()).hexdigest()
        def entry(ident,term,scope,aliases):
            return dict(id=ident,term=term,scope=scope,definition='Reviewed definition.',aliases=aliases,source=dict(path='source.md',line_start=1,line_end=1,sha256=digest),review_status='confirmed',method='explicit_definition_pattern',reviewer='Example reviewer',reviewed_at='2026-10-22T10:00:00Z')
        return entry

    def test_ambiguous_marker_never_picks_a_replacement(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); entry=self.fixture(root)
            glossary=dict(schema_version=1,entries=[entry('one','Workspace','global',['space']),entry('two','Project','product',['space'])])
            (root/'guide.md').write_text('Use [[term:space]].\n')
            report=check_documents(glossary,root,['guide.md'],'product')
            self.assertTrue(any(f['kind']=='ambiguous_lexicon' for f in report['findings']))
            self.assertFalse(any(f.get('suggestion') for f in report['findings']))

    def test_alias_marker_is_reported_once(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); entry=self.fixture(root)
            glossary=dict(schema_version=1,entries=[entry('one','Workspace','product',['team space'])])
            (root/'guide.md').write_text('Use [[term:team space]].\n')
            report=check_documents(glossary,root,['guide.md'],'product')
            aliases=[f for f in report['findings'] if f['kind']=='discouraged_alias']
            self.assertEqual(len(aliases),1)

    def test_impossible_approval_date_is_invalid(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); entry=self.fixture(root)
            data=entry('one','Workspace','product',[])
            data['reviewed_at']='2026-99-99T25:00:00Z'
            with self.assertRaises(LexiconError):
                validate_glossary(dict(schema_version=1,entries=[data]))

    def test_shorter_backticks_do_not_close_a_long_fence(self):
        from org_lexicon.core import extract_candidates
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'source.md').write_text('````markdown\n```\n**Hidden**: A code example.\n````\n**Visible**: An actual definition.\n')
            result=extract_candidates(root,['source.md'],'product')
            self.assertEqual([c['term'] for c in result['candidates']],['Visible'])

    def test_changed_candidate_is_not_silently_treated_as_reapproval(self):
        from org_lexicon.core import approve_candidate, extract_candidates
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'source.md').write_text('**Workspace**: A collection of projects.\n')
            candidates=extract_candidates(root,['source.md'],'product')
            ident=candidates['candidates'][0]['id']
            glossary=approve_candidate(candidates,None,ident,'Reviewer','2026-10-22T10:00:00Z')
            candidates['candidates'][0]['aliases']=['team space']
            with self.assertRaises(LexiconError):
                approve_candidate(candidates,glossary,ident,'Reviewer','2026-10-22T10:00:00Z')

    def test_invalid_cited_range_is_reported_even_when_hash_matches(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); entry=self.fixture(root)
            data=entry('one','Workspace','product',[])
            data['source']['line_end']=999
            (root/'guide.md').write_text('Workspace.\n')
            report=check_documents(dict(schema_version=1,entries=[data]),root,['guide.md'],'product')
            self.assertIn('invalid_definition_source_range',[f['kind'] for f in report['findings']])

    def test_extract_cannot_overwrite_source_through_symlink(self):
        import contextlib, io
        from org_lexicon.cli import main
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source=root/'source.md'; source.write_text('**Workspace**: A set of projects.\n')
            alias=root/'alias.json'; alias.symlink_to(source)
            before=source.read_bytes()
            with contextlib.redirect_stderr(io.StringIO()):
                code=main(['extract','--root',str(root),'--scope','product','--file','source.md','--out',str(alias)])
            self.assertEqual(code,2)
            self.assertEqual(source.read_bytes(),before)
