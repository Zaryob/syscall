// SPDX-License-Identifier: GPL-2.0-only
import assert from 'node:assert/strict';
import test from 'node:test';
import { readRoute, routeURL } from '../public/navigation.mjs';

test('URL round trip preserves bilingual search, view, flags and removed detail identity under a baseurl', () => {
  const address = 'https://example.org/syscall-test/?lang=tr&arch=x86&kernel=v7.3&compare=v1.0&q=dosya+tanıtıcısı&hex=1&all=1&view=args#sys-v1.0%3A16%3Achown';
  const route = readRoute(address);
  assert.equal(route.tableView, true);
  assert.equal(route.state.expanded, 'v1.0:16:chown');
  assert.deepEqual(readRoute(new URL(routeURL(address, '/syscall-test/', route.state), address).href), route);
  assert.equal(new URL(routeURL(address, '/syscall-test/', route.state), address).searchParams.get('lang'), 'tr');
});

test('history parsing resets omitted state and tolerates legacy and malformed fragments', () => {
  const route = readRoute('https://example.org/?highlight=read#sys-read');
  assert.equal(route.state.query, 'read');
  assert.equal(route.state.expanded, 'read');
  assert.equal(readRoute('https://example.org/#sys-%FF').state.expanded, '');
  assert.equal(readRoute('https://example.org/?arch=x64#conventions').tableView, false);
  assert.deepEqual(readRoute('https://example.org/').state, {
    arch:'x64', kernel:null, compare:'', query:'', hex:false, all:false, view:'summary', expanded:'',
  });
});
