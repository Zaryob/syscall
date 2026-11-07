// SPDX-License-Identifier: GPL-2.0-only
import { searchSyscalls, diffSyscalls, availableArchitectures, normalizeSelection } from './catalog.mjs';
import { snapshotPath, withBase } from './paths.mjs';
import { buildExample } from './examples.mjs';
import { syscallNote } from './notes.mjs';

const { t, apply: applyLanguage } = window.ZaryobI18n;
const $ = id => document.getElementById(id);
const rootPath = document.querySelector('meta[name="site-root"]').content;
const sitePath = path => withBase(rootPath, path);
const params = new URLSearchParams(location.search);
const librarySections = ['#title', '#architectures', '#conventions', '#api', '#sources'];
const tableView = !librarySections.includes(location.hash) &&
  (location.hash === '#reference' || location.hash.startsWith('#sys-') ||
    ['arch', 'kernel', 'compare', 'q', 'view', 'hex', 'all', 'full'].some(name => params.has(name)));

function referenceURL(values = {}, hash = '') {
  const query = new URLSearchParams(values);
  if (new URLSearchParams(location.search).has('lang')) query.set('lang', window.ZaryobI18n.language);
  return rootPath + (query.size ? '?' + query : '') + hash;
}
function linkedCall() {
  if (!location.hash.startsWith('#sys-')) return '';
  try { return decodeURIComponent(location.hash.slice(5)); }
  catch { return ''; }
}
const state = {
  arch: params.get('arch') || 'x64',
  kernel: params.get('kernel'), compare: params.get('compare') || '',
  query: params.get('q') || params.get('highlight') || '', hex: params.get('hex') === '1', all: params.get('all') === '1',
  view: params.get('view') === 'args' ? 'args' : 'summary',
  sort: 'number', direction: 1, expanded: linkedCall(),
};
const cache = new Map();
let manifest, snapshot, previous, requestId = 0;
let comparison, tableRows = new Map();
let comparisonLoad = '';
const changeLabels = {
  status: 'Implementation status', entry: 'Entry point', compat_entry: 'Compatibility entry point',
  oabi_entry: 'OABI entry point', noreturn: 'No-return marker', signature_resolution: 'Declaration availability',
  argument_count: 'Parameter count', argument_types: 'Parameter types', argument_names: 'Parameter names',
  parameters: 'Parameter declarations', declaration: 'C declaration',
};
const unresolvedLabels = {
  configuration_dependent: 'The C declaration depends on the kernel configuration.',
  wrapper_entry: 'The kernel table points to a wrapper. Its C declaration is unavailable.',
  not_found: 'C declaration not found in the imported kernel sources.',
};
const datasetPath = (kernel, file) => sitePath(snapshotPath(manifest, kernel, file));
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const nr = number => state.hex ? `0x${number.toString(16)}` : String(number);
const sourceLink = (source, kernel) => {
  const data = kernel === snapshot?.kernel ? snapshot : previous;
  return data?.provenance.archive || data?.provenance.kind === 'local'
    ? datasetPath(kernel, `sources/${source.path}`)
    : `https://github.com/torvalds/linux/blob/${encodeURIComponent(kernel)}/${source.path}#L${source.line}`;
};
const noteFor = row => row.status === 'unimplemented' ? undefined : syscallNote(row.name);
const description = (row, kernel) => {
  const note = noteFor(row);
  if (note) return esc(note[window.ZaryobI18n.language]);
  if (row.status === 'unimplemented') return esc(t('This slot is unimplemented.'));
  return `<a href="${esc(sourceLink(row.source, kernel))}" aria-label="${esc(t('Kernel source for {name}', { name: row.name }))}">${esc(t('View kernel source'))}</a>`;
};
const argumentLocations = c => [...c.registers, ...(c.stack_slots ?? []).map(n => `${t('Stack')} (${n})`)];
const key = row => `${row.number}:${row.name}`;
const rowId = row => `${row._kernel}:${key(row)}`;
const rowHash = id => `#sys-${encodeURIComponent(id)}`;

function prepareRows() {
  comparison = previous ? diffSyscalls(previous.syscalls, snapshot.syscalls) : null;
  const added = new Set(comparison?.added.map(key));
  const changed = new Map(comparison?.changed.map(change => [key(change.after), change]));
  const current = snapshot.syscalls.map(row => {
    const change = changed.get(key(row));
    return { ...row, _kernel: snapshot.kernel, _before: change?.before, _reasons: change?.reasons, _change: change ? 'changed' : added.has(key(row)) ? 'added' : '' };
  });
  const removed = comparison?.removed.map(row => ({ ...row, _kernel: previous.kernel, _change: 'removed' })) ?? [];
  tableRows = new Map([...current, ...removed].map(row => [rowId(row), row]));
}

function resolveCall(id) {
  if (!id || tableRows.has(id)) return id;
  // Legacy links select the first visible match, with the current release first.
  const matches = [...tableRows.values()].filter(row => row.name === id);
  const visible = searchSyscalls(matches.filter(row => state.all || row.status !== 'unimplemented'), state.query);
  const row = visible[0] ?? matches[0];
  return row ? rowId(row) : '';
}

async function getJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(t('Could not read {url} (HTTP {status}).', { url, status: response.status }));
  return response.json();
}
function getSnapshot(kernel, arch) {
  const url = datasetPath(kernel, `${arch}.json`);
  if (!cache.has(url)) {
    const pending = getJSON(url).then(data => {
      if (data?.kernel !== kernel || data.architecture !== arch || !Array.isArray(data.syscalls)) {
        throw new Error(t('Invalid kernel table at {url}.', { url }));
      }
      return data;
    }).catch(error => { cache.delete(url); throw error; });
    cache.set(url, pending);
  }
  return cache.get(url);
}
function saveURL(updateDetail = false) {
  const p = new URLSearchParams({ arch: state.arch, kernel: state.kernel });
  if (new URLSearchParams(location.search).has('lang')) p.set('lang', window.ZaryobI18n.language);
  if (state.compare) p.set('compare', state.compare);
  if (state.query) p.set('q', state.query);
  if (state.view === 'args') p.set('view', 'args');
  if (state.hex) p.set('hex', '1');
  if (state.all) p.set('all', '1');
  const hash = updateDetail || location.hash.startsWith('#sys-')
    ? state.expanded ? rowHash(state.expanded) : ''
    : location.hash;
  history.replaceState(null, '', `${rootPath}?${p}${hash}`);
}
function renderView() {
  const args = state.view === 'args';
  $('syscall-table').dataset.view = state.view;
  $('syscall-table').querySelectorAll('.argument-heading').forEach(th => { th.hidden = !args; });
  $('syscall-table').querySelector('.summary-heading').hidden = args;
  $('table-views').querySelectorAll('button').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.view === state.view));
  });
  $('scroll-hint').hidden = $('args-footnote').hidden = !args;
  $('convention-strip').hidden = !args || !snapshot;
  $('abi-note').hidden = !args || snapshot?.calling_convention.bits !== 32;
}
function setView(view) {
  if (state.view === view) return;
  state.view = view;
  $('table-scroll').scrollLeft = 0;
  renderRows(); saveURL();
}
function updateSelects() {
  const picker = $('architecture-picker');
  if (picker) {
    picker.replaceChildren(...manifest.architectures.map(
      a => new Option(a.label, a.id, false, a.id === state.arch)
    ));
    picker.disabled = false;
  }
  const releases = manifest.versions.filter(version => availableArchitectures(manifest, version).includes(state.arch));
  $('kernel').replaceChildren(...releases.map(version => new Option(version.slice(1), version, false, version === state.kernel)));
  $('compare').replaceChildren(new Option(t('None'), ''), ...releases.filter(version => version !== state.kernel).map(
    version => new Option(version.slice(1), version, false, version === state.compare)
  ));
  $('kernel').disabled = false;
  $('compare').disabled = releases.length < 2;
}
function renderMetadata() {
  const c = snapshot.calling_convention;
  $('table-title').textContent = t('{arch} system calls', { arch: c.label });
  document.title = `${c.label} · Linux ${state.kernel.slice(1)} · ${t('System Call Reference')}`;
  const conventions = [[t('ENTRY'), c.instruction], ['NR', c.nr], [t('RETURN'), c.result],
    [t('Argument locations'), argumentLocations(c).join(' · ')]];
  if (c.error_flag) conventions.push([t('Error flag'), c.error_flag]);
  $('convention-strip').innerHTML = conventions.map(([label, value]) =>
    `<span><strong>${esc(label)}</strong> <code>${esc(value)}</code></span>`).join('');
  for (let i = 0; i < 6; i++) {
    $(`arg-register-${i}`).textContent = c.bits === 64 ? c.registers[i] : '';
  }
  const download = datasetPath(state.kernel, `${state.arch}.json`);
  $('download').href = download;
  $('download').hidden = false;
  $('download').download = `linux-${state.kernel}-${state.arch}.json`;

}
function detailHTML(row, id) {
  const kernel = row._kernel;
  const signature = row.declaration;
  const data = row._change === 'removed' ? previous : snapshot;
  const c = data.calling_convention;
  const regInfo = row.arguments === null ? '<p class="muted"><span data-i18n="Argument details are not resolved in the imported headers.">Argument details are not resolved in the imported headers.</span></p>' : row.arguments.length
    ? `<table class="argument-table"><caption>${esc(t('Arguments to {name}', { name: row.name }))}</caption><thead><tr><th scope="col"><span data-i18n="Position">Position</span></th><th scope="col"><span data-i18n="Kernel C declaration">Kernel C declaration</span></th><th scope="col"><span data-i18n="Register">Register</span></th></tr></thead><tbody>${row.arguments.map((arg, i) => `<tr><th scope="row">ARG${i + 1}</th><td><code>${esc(arg)}</code></td><td><code>${c.bits === 64 ? esc(c.registers[i]) : t("ABI-dependent")}</code></td></tr>`).join('')}</tbody></table>${c.bits === 32 ? '<p class="small"><span data-i18n="These are logical C parameters. Register packing on this 32-bit ABI must be checked separately.">These are logical C parameters. Register packing on this 32-bit ABI must be checked separately.</span></p>' : ''}` : '<p class="muted"><span data-i18n="This syscall has no C arguments.">This syscall has no C arguments.</span></p>';
  const example = buildExample(row, data);
  const exampleHTML = example.code
    ? `<details class="example-panel"><summary>${example.kind === 'example' ? t("C usage example") : t("Generate a C skeleton")}</summary><p>${esc(t(example.reason))}</p><pre><code>${esc(example.code)}</code></pre><p><button class="text-button" data-example="${row.number}" data-kernel="${kernel}">${esc(t('Download C {kind}', { kind: t(example.kind === 'example' ? 'example' : 'skeleton') }))}</button> · <a href="https://man7.org/linux/man-pages/man2/syscall.2.html"><span data-i18n="About the libc syscall() interface">About the libc syscall() interface</span></a></p></details>`
    : `<p class="example-unavailable"><strong><span data-i18n="C example:">C example:</span></strong> ${esc(t(example.reason))}</p>`;
  const source = `<a href="${esc(sourceLink(row.source, kernel))}">${esc(row.source.path)}:${row.source.line}</a>`;
  const sourceLabel = row.signature_source?.kind === 'syscall_macro' ? 'Syscall definition:' : 'Declaration:';
  const declaration = row.signature_source ? ` · ${esc(t(sourceLabel))} <a href="${esc(sourceLink(row.signature_source, kernel))}">${esc(row.signature_source.path)}:${row.signature_source.line}</a>` : '';
  const manual = row.man_url;
  const [, manualName, manualSection] = manual?.match(/\/([^/]+)\.([23])\.html$/) || [];
  const manualHTML = manual && manualName
    ? `<a href="${esc(manual)}">${esc(t('Read {name}({section})', { name: manualName, section: manualSection }))}</a>`
    : `<span class="muted">${window.ZaryobI18n.language === 'tr' ? 'Bu girdi için man sayfası bağlantısı yok.' : 'No manual link is available for this entry.'}</span>`;
  const signatureHTML = !signature ? `<p class="muted">${esc(t(unresolvedLabels[row.signature_status] ?? 'C declaration not resolved in the imported headers.'))}</p>`
    : `<div class="signature"><button type="button" data-copy-signature aria-label="${esc(t('Copy C declaration'))}">${esc(t('Copy'))}</button><code>${esc(signature)}</code><span class="console-sr-only" role="status"></span></div>`;
  const raw = datasetPath(kernel, `${state.arch}.json`);
  const before = row._before;
  const permalink = referenceURL({ arch: state.arch, kernel, ...(row.status === 'unimplemented' ? { all: '1' } : {}) }, rowHash(id));
  const previousSignature = before ? `<p><strong>${esc(t('In Linux {version}:', { version: state.compare.slice(1) }))}</strong>
    ${before.declaration ? `<code>${esc(before.declaration)}</code>`
      : `<code>${esc(before.entry)}</code>, ${esc(before.arguments === null ? t('signature unresolved') : before.arguments.join(', ') || 'void')}`}</p>` : '';
  const reasons = row._reasons?.map(reason => t(changeLabels[reason])).join(' · ');
  const entryMetadata = [
    row.compat_entry && `${esc(t('Compatibility entry point'))} <code>${esc(row.compat_entry)}</code>`,
    row.oabi_entry && `${esc(t('OABI entry point'))} <code>${esc(row.oabi_entry)}</code>`,
    row.noreturn && esc(t('This syscall does not return.')),
  ].filter(Boolean);
  return `<tr class="detail-row" id="detail-${esc(id)}"><td colspan="${state.view === 'args' ? 8 : 3}">
    <div class="detail-content">
      <h3>${esc(row.name)} <span class="normal">/ ${esc(state.arch)} / Linux ${kernel.slice(1)}</span></h3>
      <p class="detail-description">${description(row, kernel)}</p>
      ${signatureHTML}${regInfo}
      <p><strong><span data-i18n="Entry point:">Entry point:</span></strong> <code>${esc(row.entry || t('none'))}</code>
        · <strong><span data-i18n="Number:">Number:</span></strong> ${row.number} / 0x${row.number.toString(16)}
        · <strong>ABI:</strong> <code>${esc(row.abi)}</code></p>
      ${entryMetadata.length ? `<p>${entryMetadata.join(' · ')}</p>` : ''}
      ${reasons ? `<p><strong>${esc(t('Changes:'))}</strong> ${esc(reasons)}</p>` : ''}
      ${row.status === 'unimplemented' ? '<p><span data-i18n="This table slot has no implementation. It must not be treated as an available syscall.">This table slot has no implementation. It must not be treated as an available syscall.</span></p>' : ''}
      ${row.signature_note && !row.signature_status ? `<p>${esc(t(row.signature_note))}</p>` : ''}${previousSignature}
      <p><strong><span data-i18n="Kernel table:">Kernel table:</span></strong> ${source}${declaration}</p>
      <p>${manualHTML}
        · <button class="text-button" data-export="${row.number}" data-kernel="${kernel}"><span data-i18n="Download entry JSON">Download entry JSON</span></button>
        · <a href="${esc(raw)}"><span data-i18n="Table JSON">Table JSON</span></a>
        · <a href="${esc(permalink)}"><span data-i18n="Permanent link">Permanent link</span></a></p>
      ${exampleHTML}
    </div></td></tr>`;
}

function updateDetail(id, expanded) {
  const row = document.getElementById(`sys-${id}`);
  if (!row) return;
  const button = row.querySelector('[data-call]');
  button.setAttribute('aria-expanded', String(expanded));
  button.firstElementChild.textContent = expanded ? '▾' : '▸';
  const detailId = `detail-${id}`;
  if (expanded) {
    button.setAttribute('aria-controls', detailId);
    row.insertAdjacentHTML('afterend', detailHTML(tableRows.get(id), id));
    applyLanguage(document.getElementById(detailId));
  } else {
    button.removeAttribute('aria-controls');
    document.getElementById(detailId)?.remove();
  }
}

function setExpanded(id) {
  if (id === state.expanded) return;
  updateDetail(state.expanded, false);
  state.expanded = id;
  updateDetail(id, true);
}

function highlightMatch(text, q) {
  if (!q) return esc(text);
  const terms = q.trim().split(/\s+/).filter(Boolean).map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  if (!terms.length) return esc(text);
  const regex = new RegExp(`(${terms.join('|')})`, 'gi');
  return esc(text).replace(regex, '<mark class="console-highlight">$1</mark>');
}

function renderRows() {
  renderView();
  if (!snapshot) return;
  if (comparison) {
    $('diff-note').textContent = t('Compared with Linux {version}: {added} added, {removed} removed, {changed} changed entries. Changes include reserved or unimplemented slots. Unchanged entries remain visible for context.', { version: state.compare.slice(1), added: comparison.added.length, removed: comparison.removed.length, changed: comparison.changed.length });
  }
  $('diff-note').hidden = !comparison;
  const allRows = [...tableRows.values()];
  const eligible = state.all ? allRows : allRows.filter(row => row.status !== 'unimplemented');
  const rows = searchSyscalls(eligible, state.query);
  rows.sort((a, b) => state.direction * (state.sort === 'number' ? a.number - b.number : a.name.localeCompare(b.name)));
  $('rows').innerHTML = rows.map(row => {
    const id = esc(rowId(row));
    const args = state.view === 'summary' ? '' : row.arguments === null ? '<td colspan="6" class="muted"><span data-i18n="not resolved">not resolved</span></td>' : Array.from({ length: 6 }, (_, i) => `<td class="arg-cell">${row.arguments[i] ? `<code>${esc(row.arguments[i])}</code>` : '<span class="muted" aria-label="no argument" data-i18n-aria-label="no argument">—</span>'}</td>`).join('');
    const badge = row._change ? `<span class="badge ${row._change}">${esc(t(row._change))}</span>` : row.status === 'unimplemented' ? '<span class="badge unimplemented"><span data-i18n="unimplemented">unimplemented</span></span>' : '';
    const trailing = state.view === 'args'
      ? args
      : `<td class="row-description${noteFor(row) ? '' : ' muted'}">${description(row, row._change === 'removed' ? state.compare : state.kernel)}</td>`;
    return `<tr class="syscall-row" id="sys-${id}"><td class="call-number">${nr(row.number)}</td>
      <th scope="row" class="call-identity"><button class="call-name" data-call="${id}" aria-expanded="false">
        <span aria-hidden="true">▸</span><span>${highlightMatch(row.name, state.query)}</span></button>${badge}</th>${trailing}</tr>`;
  }).join('');
  $('results').textContent = t('{count} of {total} entries', { count: rows.length, total: eligible.length });
  applyLanguage($('rows'));
  if (state.expanded) updateDetail(state.expanded, true);
  $('empty').hidden = rows.length > 0;
  for (const sort of ['number', 'name']) {
    const button = $(`sort-${sort}`);
    const active = sort === state.sort;
    button.parentElement.setAttribute('aria-sort', active ? (state.direction === 1 ? 'ascending' : 'descending') : 'none');
    button.textContent = `${t(sort === 'number' ? 'No.' : 'System call')}${active ? (state.direction === 1 ? ' ↑' : ' ↓') : ''}`;
  }
}

function renderComparisonStatus() {
  $('compare-status').hidden = !comparisonLoad;
  $('retry-compare').hidden = comparisonLoad !== 'failed';
  const message = comparisonLoad === 'failed'
    ? 'Could not load the comparison with Linux {version}.'
    : 'Loading comparison with Linux {version}…';
  $('compare-message').textContent = comparisonLoad ? t(message, { version: state.compare.slice(1) }) : '';
}

async function finishComparison(id, pending) {
  const old = await pending;
  if (id !== requestId) return;
  comparisonLoad = old ? '' : 'failed';
  renderComparisonStatus();
  if (!old) {
    state.expanded = resolveCall(state.expanded) || state.expanded;
    if (state.expanded && tableRows.has(state.expanded) && !document.getElementById(`detail-${state.expanded}`)) {
      updateDetail(state.expanded, true);
    }
    return;
  }
  const focused = document.activeElement?.closest('[data-call]')?.dataset.call;
  previous = old;
  prepareRows();
  state.expanded = resolveCall(state.expanded);
  if (!state.expanded && linkedCall()) saveURL(true);
  renderRows();
  if (focused) document.getElementById(`sys-${focused}`)?.querySelector('[data-call]')?.focus({ preventScroll: true });
}

async function refresh() {
  normalizeSelection(manifest, state);
  const id = ++requestId;
  $('error').hidden = true;
  $('results').textContent = t("Loading kernel table\u2026");
  $('syscall-table').setAttribute('aria-busy', 'true');
  // Remove the previous table immediately so a failed load cannot masquerade as the selected release.
  snapshot = previous = null;
  renderView();
  $('rows').replaceChildren();
  $('empty').hidden = true;
  $('diff-note').hidden = true;
  comparisonLoad = '';
  renderComparisonStatus();
  $('download').hidden = true;
  updateSelects();
  const arch = manifest.architectures.find(a => a.id === state.arch);
  $('table-title').textContent = t('{arch} system calls', { arch: arch.label });
  saveURL();
  const pending = state.compare ? getSnapshot(state.compare, state.arch).catch(() => null) : null;
  try {
    const next = await getSnapshot(state.kernel, state.arch);
    if (id !== requestId) return;
    snapshot = next;
    prepareRows();
    if (!pending) {
      state.expanded = resolveCall(state.expanded);
      if (!state.expanded && linkedCall()) saveURL(true);
    }
    renderMetadata(); renderRows();
  } catch (error) {
    if (id !== requestId) return;
    $('error').textContent = `${error.message} ${t('Check that the dataset exists, then reload to retry.')}`;
    $('error').hidden = false;
    $('results').textContent = t("Table unavailable");
    return;
  } finally {
    if (id === requestId) $('syscall-table').removeAttribute('aria-busy');
  }
  if (pending) {
    comparisonLoad = 'loading';
    renderComparisonStatus();
    await finishComparison(id, pending);
  }
}

function resetSearch() {
  state.query = ''; state.expanded = '';
  $('search').value = '';
  renderRows(); saveURL(); $('search').focus();
}
function downloadFile(text, type, filename) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = filename;
  document.body.append(anchor); anchor.click(); anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$('architecture-picker')?.addEventListener('change', () => {
  state.arch = $('architecture-picker').value;
  const availableVersions = manifest.versions.filter(v => availableArchitectures(manifest, v).includes(state.arch));
  if (!availableVersions.includes(state.kernel)) {
    state.kernel = availableVersions[0] || manifest.latest;
  }
  if (state.compare && (!availableVersions.includes(state.compare) || state.compare === state.kernel)) {
    state.compare = '';
  }
  state.expanded = ''; refresh();
});
$('kernel').addEventListener('change', () => {
  state.kernel = $('kernel').value;
  if (state.compare === state.kernel) state.compare = '';
  state.expanded = ''; refresh();
});
$('compare').addEventListener('change', () => { state.compare = $('compare').value; refresh(); });
$('retry-compare').addEventListener('click', () => {
  comparisonLoad = 'loading';
  $('compare').focus();
  renderComparisonStatus();
  finishComparison(requestId, getSnapshot(state.compare, state.arch).catch(() => null));
});
$('search-form').addEventListener('submit', event => {
  event.preventDefault();
});
$('table-views').addEventListener('click', event => {
  const button = event.target.closest('[data-view]');
  if (button) setView(button.dataset.view);
});
$('search').addEventListener('input', () => {
  state.query = $('search').value; state.expanded = '';
  renderRows(); saveURL();
});
$('clear').addEventListener('click', resetSearch);
$('reset-search').addEventListener('click', resetSearch);
$('hex').addEventListener('change', () => { state.hex = $('hex').checked; renderRows(); saveURL(); });
$('show-unimplemented').addEventListener('change', () => { state.all = $('show-unimplemented').checked; renderRows(); saveURL(); });
for (const sort of ['number', 'name']) $(`sort-${sort}`).addEventListener('click', () => {
  state.direction = state.sort === sort ? -state.direction : 1; state.sort = sort; renderRows();
});
$('rows').addEventListener('click', event => {
  const exampleButton = event.target.closest('[data-example]');
  if (exampleButton) {
    const data = exampleButton.dataset.kernel === state.kernel ? snapshot : previous;
    const row = data?.syscalls.find(r => r.number === Number(exampleButton.dataset.example));
    if (!row) return;
    const example = buildExample(row, data);
    if (example.code) downloadFile(example.code, 'text/x-c', example.filename);
    return;
  }
  const exportButton = event.target.closest('[data-export]');
  if (exportButton) {
    const data = exportButton.dataset.kernel === state.kernel ? snapshot : previous;
    const row = data?.syscalls.find(r => r.number === Number(exportButton.dataset.export));
    if (!row) return;
    const { syscalls, ...metadata } = data;
    downloadFile(JSON.stringify({ ...metadata, ...row }, null, 2) + '\n', 'application/json', `${data.architecture}-${data.kernel}-${row.name}.json`);
    return;
  }
  const button = event.target.closest('[data-call]');
  if (!button) return;
  const id = button.dataset.call;
  setExpanded(state.expanded === id ? '' : id);
  saveURL(true);
});
$('rows').addEventListener('click', async event => {
  const button = event.target.closest('[data-copy-signature]');
  if (!button) return;
  const signature = button.parentElement;
  const code = signature.querySelector('code');
  let result;
  try {
    await navigator.clipboard.writeText(code.textContent);
    result = t('Copied');
  } catch {
    const range = document.createRange();
    range.selectNodeContents(code);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);
    result = t('Select code to copy');
  }
  button.textContent = result;
  signature.querySelector('[role="status"]').textContent = result;
});
function renderLibrary() {
  const links = new Map(manifest.architectures.map(arch => {
    const kernel = manifest.versions.find(version => availableArchitectures(manifest, version).includes(arch.id));
    return [arch.id, esc(referenceURL({ arch: arch.id, kernel }))];
  }));
  $('architecture-links').innerHTML = manifest.architectures.map(arch =>
    `<li><a href="${links.get(arch.id)}">${esc(arch.label)}</a></li>`
  ).join('');
  $('convention-rows').innerHTML = manifest.architectures.map(a =>
    `<tr><th scope="row"><a href="${links.get(a.id)}">${esc(a.label)}</a></th><td>${esc(a.instruction)}</td><td>${esc(a.nr)}</td><td>${esc(a.result)}</td><td>${esc(argumentLocations(a).join(', '))}</td><td>${esc(a.error_flag ?? '—')}</td></tr>`
  ).join('');
  const download = datasetPath(manifest.latest, 'x64.json');
  $('bulk-link').href = download;
  $('api-example').textContent = `curl '${location.origin}${download}'`;
  $('snapshot-sources').href = datasetPath(manifest.latest, 'sources.json');
}
window.addEventListener('zaryob:language', () => {
  if (!manifest) return;
  if (!tableView) {
    renderLibrary();
    return;
  }
  $('back-to-architectures').href = referenceURL({}, '#architectures');
  updateSelects(); saveURL();
  renderComparisonStatus();
  if (snapshot) { renderMetadata(); renderRows(); }
});
window.addEventListener('hashchange', () => {
  if (!tableView) return;
  if (!snapshot) {
    state.expanded = linkedCall();
    return;
  }
  setExpanded(resolveCall(linkedCall()));
  document.getElementById(`sys-${state.expanded}`)?.scrollIntoView({ block: 'center' });
});

$('library').hidden = tableView;
$('reference').hidden = !tableView;
try {
  manifest = await getJSON(sitePath('data/manifest.json'));
  if (tableView) {
    $('back-to-architectures').href = referenceURL({}, '#architectures');
    $('search').value = state.query;
    $('hex').checked = state.hex;
    $('show-unimplemented').checked = state.all;
    await refresh();
    if (state.expanded) document.getElementById(`sys-${state.expanded}`)?.scrollIntoView({ block: 'center' });
    else if (location.hash === '#reference' || state.query) $('reference').scrollIntoView({ behavior: 'smooth' });
  } else {
    renderLibrary();
    if (librarySections.includes(location.hash)) $(location.hash.slice(1)).scrollIntoView({ behavior: 'instant' });
  }
} catch (error) {
  const alert = $(tableView ? 'error' : 'library-error');
  alert.textContent = `${error.message} ${t('Check the site deployment and data/manifest.json, then reload to retry.')}`;
  alert.hidden = false;
  if (tableView) $('results').textContent = t('Dataset unavailable');
}
