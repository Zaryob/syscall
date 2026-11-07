#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Refresh the manual-page name catalog used by the offline kernel importer."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import urllib.request

CATALOG = Path(__file__).resolve().parents[1] / 'sources/manual-pages.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Compare page names without writing')
    args = parser.parse_args()
    catalog = json.loads(CATALOG.read_text())
    sections, sources = {}, []
    for section in ['2', '3']:
        url = f'https://man7.org/linux/man-pages/dir_section_{section}.html'
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read()
        names = set(re.findall(rf'href="(?:\./)?man{section}/([^"/]+)\.{section}\.html"', data.decode()))
        if len(names) < 200:
            raise ValueError('Incomplete manual index: ' + url)
        if section == '3':
            # Section 3 is used only by the explicit editorial aliases.
            requested = {target[:-2] for target in catalog['aliases'].values() if target.endswith('.3')}
            names &= requested
        sections[section] = sorted(names)
        sources.append({'url': url, 'sha256': hashlib.sha256(data).hexdigest()})
    if args.check:
        if sections != catalog['sections']:
            raise SystemExit('Manual-page catalog changed; refresh it before regenerating tables.')
        print('Manual-page catalog matches the upstream page names.')
        return
    catalog.update(sections=sections, sources=sources)
    CATALOG.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + '\n')
    print('Updated manual-page names; regenerate kernel snapshots to apply new links.')


if __name__ == '__main__':
    main()
