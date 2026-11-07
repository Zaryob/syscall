// SPDX-License-Identifier: GPL-2.0-only
// URL state is independent of loaded snapshots, including during back/forward.
export function readRoute(address) {
  const url = new URL(address), p = url.searchParams;
  let expanded = '';
  if (url.hash.startsWith('#sys-')) {
    try { expanded = decodeURIComponent(url.hash.slice(5)); } catch { /* Invalid fragment. */ }
  }
  const library = ['#title', '#architectures', '#conventions', '#api', '#sources'].includes(url.hash);
  return {
    tableView: !library && (url.hash === '#reference' || url.hash.startsWith('#sys-') ||
      ['arch', 'kernel', 'compare', 'q', 'highlight', 'view', 'hex', 'all', 'full'].some(key => p.has(key))),
    state: {
      arch: p.get('arch') || 'x64', kernel: p.get('kernel'), compare: p.get('compare') || '',
      query: p.get('q') || p.get('highlight') || '', hex: p.get('hex') === '1', all: p.get('all') === '1',
      view: p.get('view') === 'args' ? 'args' : 'summary', expanded,
    },
  };
}
export function routeURL(address, root, state, updateDetail = false) {
  const url = new URL(address);
  const p = new URLSearchParams({ arch: state.arch, kernel: state.kernel });
  // Keep the explicit language in this history entry, not a stored preference.
  if (url.searchParams.has('lang')) p.set('lang', url.searchParams.get('lang'));
  if (state.compare) p.set('compare', state.compare);
  if (state.query) p.set('q', state.query);
  if (state.view === 'args') p.set('view', 'args');
  if (state.hex) p.set('hex', '1');
  if (state.all) p.set('all', '1');
  const hash = updateDetail || url.hash.startsWith('#sys-')
    ? state.expanded ? '#sys-' + encodeURIComponent(state.expanded) : '' : url.hash;
  return `${root}?${p}${hash}`;
}
