# SPDX-License-Identifier: GPL-2.0-only
"""Validate the system call introduction catalog and helper."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sync_introductions', ROOT / 'scripts/sync_introductions.py')
sync_introductions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_introductions)


class IntroductionsTests(unittest.TestCase):
    def setUp(self):
        self.catalog_path = ROOT / 'sources/introductions.json'
        self.assertTrue(self.catalog_path.is_file(), 'sources/introductions.json must exist')
        self.catalog = json.loads(self.catalog_path.read_bytes())

    def test_schema_and_coverage(self):
        self.assertEqual(self.catalog.get('schema_version'), 1)
        self.assertIn('introductions', self.catalog)
        intros = self.catalog['introductions']
        self.assertGreater(len(intros), 500)

        defined_names = sync_introductions.load_bundled_names()
        self.assertTrue(sync_introductions.validate_catalog(self.catalog, defined_names))

    def test_openat_introduction_is_accurate(self):
        intros = self.catalog['introductions']
        self.assertEqual(intros['openat'], {'version': '2.6.16'})
        self.assertEqual(intros['openat2'], {'version': '5.6'})
        self.assertEqual(intros['clone3'], {'version': '5.3'})
        self.assertEqual(intros['bpf'], {'version': '3.18'})
        self.assertEqual(intros['read'], {'version': '1.0'})

    def test_notes_are_bilingual(self):
        for name, entry in self.catalog['introductions'].items():
            if 'note' in entry:
                self.assertIn('note_tr', entry, f'{name} missing note_tr')
                self.assertTrue(entry['note'].strip())
                self.assertTrue(entry['note_tr'].strip())


if __name__ == '__main__':
    unittest.main()
