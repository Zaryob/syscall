import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs

spec = importlib.util.spec_from_file_location('prepare_site', Path(__file__).resolve().parents[1] / 'scripts/prepare_site.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class PrepareTests(unittest.TestCase):
    def test_latest_revision_drives_static_metadata_and_portable_search_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public = root / 'public'
            folder = public / 'data/revisions/v9.0/fixture'
            folder.mkdir(parents=True)
            manifest = {'latest': 'v9.0', 'versions': ['v9.0'],
                        'version_paths': {'v9.0': 'revisions/v9.0/fixture'},
                        'version_architectures': {'v9.0': ['x64']},
                        'architectures': [{'id': 'x64', 'label': 'x86-64'}]}
            (public / 'data/manifest.json').write_text(json.dumps(manifest))
            (folder / 'x64.json').write_text(json.dumps({'syscalls': [
                {'number': 0, 'name': 'read', 'status': 'defined', 'declaration': 'long sys_read(void);'},
                {'number': 1, 'name': 'unused', 'status': 'unimplemented'},
            ]}))
            (public / 'notes.mjs').write_text("const entries = [\n  ['read', 'Read bytes.', 'Bayt okur.'],\n];\n")
            with patch.multiple(prepare, ROOT=root, PUBLIC=public, ARCHIVE=public / 'downloads/source.tar.gz'):
                prepare.prepare()
            metadata = json.loads((public / '_data/syscall_release.json').read_text())
            self.assertEqual(metadata['latest'], 'v9.0')
            self.assertEqual(metadata['latest_path'], 'revisions/v9.0/fixture')
            entries = json.loads((public / 'search.json').read_text())
            self.assertEqual(len(entries), 2)
            self.assertEqual({e['lang']: e['description'] for e in entries},
                             {'tr': 'Bayt okur. — long sys_read(void);', 'en': 'Read bytes. — long sys_read(void);'})
            for entry in entries:
                url = urlsplit(entry['url'])
                self.assertEqual(url.path, '')
                self.assertEqual(parse_qs(url.query)['kernel'], ['v9.0'])
                self.assertEqual(url.fragment, 'sys-v9.0:0:read')

    def test_search_index_is_bilingual_covers_other_abis_and_has_no_empty_description(self):
        notes = prepare.editorial_notes()
        self.assertGreater(len(notes), 200)
        entries = json.loads((prepare.PUBLIC / 'search.json').read_text())
        by_key = {(e['title'], e['lang']): e for e in entries}
        self.assertEqual(len(by_key), len(entries))
        self.assertTrue(all(e['description'] for e in entries))
        self.assertTrue(by_key[('sys_read', 'tr')]['description'].startswith(notes['read']['tr']))
        self.assertNotEqual(by_key[('sys_read', 'tr')]['description'], by_key[('sys_read', 'en')]['description'])
        for name in ['mmap2', 'socketcall', '_llseek']:
            self.assertIn('arch=', by_key[('sys_' + name, 'en')]['url'])
            self.assertNotIn('arch=x64', by_key[('sys_' + name, 'en')]['url'])


if __name__ == '__main__':
    unittest.main()
