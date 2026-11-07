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
            with patch.multiple(prepare, ROOT=root, PUBLIC=public, ARCHIVE=public / 'downloads/source.tar.gz'):
                prepare.prepare()
            metadata = json.loads((public / '_data/syscall_release.json').read_text())
            self.assertEqual(metadata['latest'], 'v9.0')
            self.assertEqual(metadata['latest_path'], 'revisions/v9.0/fixture')
            entries = json.loads((public / 'search.json').read_text())
            self.assertEqual(len(entries), 2)
            for entry in entries:
                url = urlsplit(entry['url'])
                self.assertEqual(url.path, '')
                self.assertEqual(parse_qs(url.query)['kernel'], ['v9.0'])
                self.assertEqual(url.fragment, 'sys-v9.0:0:read')
