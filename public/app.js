// SPDX-License-Identifier: GPL-2.0-only
import { searchSyscalls, diffSyscalls, availableArchitectures, normalizeSelection } from './catalog.mjs';
import { withBase } from './paths.mjs';
import { buildExample } from './examples.mjs';

const { t, apply: applyLanguage } = window.ZaryobI18n;
const $ = id => document.getElementById(id);
const rootPath = document.querySelector('meta[name="site-root"]').content;
const sitePath = path => withBase(rootPath, path);
const params = new URLSearchParams(location.search);
const state = {
  arch: params.get('arch') || 'x64',
  kernel: params.get('kernel'), compare: params.get('compare') || '',
  query: params.get('q') || '', hex: params.get('hex') === '1', all: params.get('all') === '1',
  sort: 'number', direction: 1, expanded: location.hash.startsWith('#sys-') ? decodeURIComponent(location.hash.slice(5)) : '',
};
const cache = new Map();
let manifest, snapshot, previous, requestId = 0;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const nr = number => state.hex ? `0x${number.toString(16)}` : String(number);
const sourceLink = (source, kernel) => {
  const data = kernel === snapshot?.kernel ? snapshot : previous;
  return data?.provenance.archive
    ? sitePath(`data/${kernel}/sources/${source.path}`)
    : `https://github.com/torvalds/linux/blob/${encodeURIComponent(kernel)}/${source.path}#L${source.line}`;
};
const key = row => `${row.number}:${row.name}`;

async function getJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(t('Could not read {url} (HTTP {status}).', { url, status: response.status }));
  return response.json();
}
function getSnapshot(kernel, arch) {
  const url = sitePath(`data/${kernel}/${arch}.json`);
  if (!cache.has(url)) cache.set(url, getJSON(url).catch(error => { cache.delete(url); throw error; }));
  return cache.get(url);
}
function saveURL() {
  const p = new URLSearchParams({ arch: state.arch, kernel: state.kernel });
  if (new URLSearchParams(location.search).has('lang')) p.set('lang', window.ZaryobI18n.language);
  if (state.compare) p.set('compare', state.compare);
  if (state.query) p.set('q', state.query);
  if (state.hex) p.set('hex', '1');
  if (state.all) p.set('all', '1');
  const hash = state.expanded ? `#sys-${encodeURIComponent(state.expanded)}` : location.hash.startsWith('#sys-') ? '' : location.hash;
  history.replaceState(null, '', `${rootPath}?${p}${hash}`);
}
function updateArchitectureNav() {
  $('architectures').innerHTML = manifest.architectures.filter(a => availableArchitectures(manifest, state.kernel).includes(a.id)).map(a => `<a href="${rootPath}?arch=${a.id}&amp;kernel=${state.kernel}" data-arch="${a.id}" ${a.id === state.arch ? 'aria-current="true"' : ''}>${esc(a.id)}</a>`).join('');
}
function updateSelects() {
  $('kernel').innerHTML = manifest.versions.map(v => `<option value="${v}" ${v === state.kernel ? 'selected' : ''}>${v.slice(1)}${v === manifest.latest ? ' (' + t('Latest snapshot') + ')' : ''}</option>`).join('');
  $('compare').innerHTML = `<option value="">${t('No comparison')}</option>` + manifest.versions.filter(v => v !== state.kernel && availableArchitectures(manifest, v).includes(state.arch)).map(v => `<option value="${v}" ${v === state.compare ? 'selected' : ''}>${v.slice(1)}</option>`).join('');
  $('kernel').disabled = $('compare').disabled = false;
}
function renderMetadata() {
  const c = snapshot.calling_convention;
  document.title = `${c.label} · Linux ${state.kernel.slice(1)} · ${t('System Call Reference')}`;
  $('release-note').textContent = `Linux ${state.kernel.slice(1)} · ${c.label} · ${c.bits}-bit`;
  $('convention-strip').innerHTML = `<strong><span data-i18n="ENTRY">ENTRY</span></strong> ${esc(c.instruction)} &nbsp; | &nbsp; <strong>NR</strong> ${c.nr} &nbsp; | &nbsp; <strong><span data-i18n="RETURN">RETURN</span></strong> ${c.result} &nbsp; | &nbsp; <strong><span data-i18n="ARGUMENT REGISTERS">ARGUMENT REGISTERS</span></strong> ${c.registers.join(' → ')}`;
  applyLanguage($('convention-strip'));
  $('abi-note').hidden = c.bits !== 32;
  for (let i = 0; i < 6; i++) {
    $(`arg-register-${i}`).textContent = c.bits === 64 ? c.registers[i] : '';
  }
  const download = sitePath(`data/${state.kernel}/${state.arch}.json`);
  $('download').href = $('bulk-link').href = download;
  $('download').download = `linux-${state.kernel}-${state.arch}.json`;
  $('api-example').textContent = `curl '${location.origin}${download}'`;
  $('provenance').textContent = t('Current dataset: Linux {version}, {origin}. {count} source files recorded with SHA-256 hashes.', { version: state.kernel.slice(1), origin: t(snapshot.provenance.kind === 'local' ? 'imported from a local source tree' : snapshot.provenance.archive ? 'imported from kernel.org archives' : 'imported from torvalds/linux'), count: snapshot.provenance.files.length });
}
function detailHTML(row, removed) {
  const kernel = removed ? state.compare : state.kernel;
  const signature = row.arguments === null ? t("C declaration not resolved in the imported headers.") : `long ${row.name}(${row.arguments.length ? row.arguments.join(', ') : 'void'});`;
  const data = removed ? previous : snapshot;
  const c = data.calling_convention;
  const regInfo = row.arguments === null ? '<p class="muted"><span data-i18n="Argument details are not resolved in the imported headers.">Argument details are not resolved in the imported headers.</span></p>' : row.arguments.length
    ? `<table class="argument-table"><caption>${esc(t('Arguments to {name}', { name: row.name }))}</caption><thead><tr><th scope="col"><span data-i18n="Position">Position</span></th><th scope="col"><span data-i18n="Kernel C declaration">Kernel C declaration</span></th><th scope="col"><span data-i18n="Register">Register</span></th></tr></thead><tbody>${row.arguments.map((arg, i) => `<tr><th scope="row">ARG${i + 1}</th><td><code>${esc(arg)}</code></td><td><code>${c.bits === 64 ? c.registers[i] : t("ABI-dependent")}</code></td></tr>`).join('')}</tbody></table>${c.bits === 32 ? '<p class="small"><span data-i18n="These are logical C parameters. Register packing on this 32-bit ABI must be checked separately.">These are logical C parameters. Register packing on this 32-bit ABI must be checked separately.</span></p>' : ''}` : '<p class="muted"><span data-i18n="This syscall has no C arguments.">This syscall has no C arguments.</span></p>';
  const example = buildExample(row, data);
  const exampleHTML = example.code
    ? `<details class="example-panel"><summary>${example.kind === 'example' ? t("C usage example") : t("Generate a C skeleton")}</summary><p>${esc(t(example.reason))}</p><pre><code>${esc(example.code)}</code></pre><p><button class="text-button" data-example="${row.number}" data-kernel="${kernel}">${esc(t('Download C {kind}', { kind: t(example.kind === 'example' ? 'example' : 'skeleton') }))}</button> · <a href="https://man7.org/linux/man-pages/man2/syscall.2.html"><span data-i18n="About the libc syscall() interface">About the libc syscall() interface</span></a></p></details>`
    : `<p class="example-unavailable"><strong><span data-i18n="C example:">C example:</span></strong> ${esc(t(example.reason))}</p>`;
  const source = `<a href="${sourceLink(row.source, kernel)}">${esc(row.source.path)}:${row.source.line}</a>`;
  const declaration = row.signature_source ? ` · ${esc(t('Declaration:'))} <a href="${sourceLink(row.signature_source, kernel)}">${esc(row.signature_source.path)}:${row.signature_source.line}</a>` : '';
  const raw = sitePath(`data/${kernel}/${state.arch}.json`);
  const before = row._change === 'changed' ? previous.syscalls.find(r => key(r) === key(row)) : null;
  return `<tr class="detail-row" id="detail-${row.number}"><td colspan="9"><div class="detail-content"><h3>${esc(row.name)} <span class="normal">/ ${esc(state.arch)} / Linux ${kernel.slice(1)}</span></h3><pre><code>${esc(signature)}</code></pre>${regInfo}<p><strong><span data-i18n="Entry point:">Entry point:</span></strong> <code>${esc(row.entry || t("none"))}</code> · <strong><span data-i18n="Number:">Number:</span></strong> ${row.number} / 0x${row.number.toString(16)} · <strong>ABI:</strong> <code>${esc(row.abi)}</code></p>${row.status === 'unimplemented' ? '<p><span data-i18n="This table slot has no implementation. It must not be treated as an available syscall.">This table slot has no implementation. It must not be treated as an available syscall.</span></p>' : ''}${row.signature_note ? `<p>${esc(t(row.signature_note))}</p>` : ''}${before ? `<p><strong>${esc(t('In Linux {version}:', { version: state.compare.slice(1) }))}</strong> <code>${esc(before.entry)}</code>, ${esc(before.arguments === null ? t("signature unresolved") : before.arguments.join(', ') || 'void')}</p>` : ''}<p><strong><span data-i18n="Kernel table:">Kernel table:</span></strong> ${source}${declaration}</p><p><a href="${esc(row.man_url)}">${esc(t('Look up {name}(2)', { name: row.name }))}</a> · <button class="text-button" data-export="${row.number}" data-kernel="${kernel}"><span data-i18n="Download entry JSON">Download entry JSON</span></button> · <a href="${raw}"><span data-i18n="Table JSON">Table JSON</span></a> · <a href="${rootPath}?arch=${state.arch}&amp;kernel=${kernel}${row.status === 'unimplemented' ? '&amp;all=1' : ''}#sys-${encodeURIComponent(row.name)}"><span data-i18n="Permanent link">Permanent link</span></a></p>${exampleHTML}</div></td></tr>`;
}
function renderRows() {
  if (!snapshot) return;
  const changes = new Map();
  let allRows = snapshot.syscalls;
  if (previous) {
    const diff = diffSyscalls(previous.syscalls, snapshot.syscalls);
    diff.added.forEach(row => changes.set(key(row), 'added'));
    diff.changed.forEach(({ after }) => changes.set(key(after), 'changed'));
    allRows = [...allRows, ...diff.removed.map(row => ({ ...row, _change: 'removed' }))];
    $('diff-note').textContent = t('Compared with Linux {version}: {added} added, {removed} removed, {changed} changed entries. Changes include reserved or unimplemented slots. Unchanged entries remain visible for context.', { version: state.compare.slice(1), added: diff.added.length, removed: diff.removed.length, changed: diff.changed.length });
    $('diff-note').hidden = false;
  } else $('diff-note').hidden = true;
  const eligible = state.all ? allRows : allRows.filter(row => row.status !== 'unimplemented');
  const rows = searchSyscalls(eligible, state.query).map(row => ({ ...row, _change: row._change || changes.get(key(row)) }));
  rows.sort((a, b) => state.direction * (state.sort === 'number' ? a.number - b.number : a.name.localeCompare(b.name)));
  $('rows').innerHTML = rows.map(row => {
    const expanded = state.expanded === row.name;
    const args = row.arguments === null ? '<td colspan="6" class="muted"><span data-i18n="not resolved">not resolved</span></td>' : Array.from({ length: 6 }, (_, i) => `<td class="arg-cell">${row.arguments[i] ? `<code>${esc(row.arguments[i])}</code>` : '<span class="muted" aria-label="no argument" data-i18n-aria-label="no argument">—</span>'}</td>`).join('');
    const badge = row._change ? `<span class="badge ${row._change}">${esc(t(row._change))}</span>` : row.status === 'unimplemented' ? '<span class="badge unimplemented"><span data-i18n="unimplemented">unimplemented</span></span>' : '';
    return `<tr class="syscall-row" id="sys-${esc(row.name)}"><td>${nr(row.number)}</td><td><button class="call-name" data-name="${esc(row.name)}" aria-expanded="${expanded}" ${expanded ? `aria-controls="detail-${row.number}"` : ''}>${esc(row.name)}</button>${badge}</td>${args}<td class="man"><a href="${esc(row.man_url)}" aria-label="${esc(t('Look up {name} in Linux man-pages', { name: row.name }))}">man(2)</a></td></tr>${expanded ? detailHTML(row, row._change === 'removed') : ''}`;
  }).join('');
  $('results').textContent = t('{count} of {total} entries · {arch} / Linux {version}', { count: rows.length, total: eligible.length, arch: state.arch, version: state.kernel.slice(1) });
  applyLanguage($('rows'));
  $('empty').hidden = rows.length > 0;
  for (const sort of ['number', 'name']) {
    const button = $(`sort-${sort}`);
    const active = sort === state.sort;
    button.parentElement.setAttribute('aria-sort', active ? (state.direction === 1 ? 'ascending' : 'descending') : 'none');
    button.textContent = `${t(sort === 'number' ? 'No.' : 'System call')}${active ? (state.direction === 1 ? ' ↑' : ' ↓') : ''}`;
  }
}

async function refresh() {
  normalizeSelection(manifest, state);
  const id = ++requestId;
  $('error').hidden = true;
  $('results').textContent = t("Loading kernel table\u2026");
  $('syscall-table').setAttribute('aria-busy', 'true');
  // Remove the previous table immediately so a failed load cannot masquerade as the selected release.
  snapshot = previous = null;
  $('rows').replaceChildren();
  $('empty').hidden = true;
  $('diff-note').hidden = true;
  updateArchitectureNav();
  updateSelects();
  saveURL();
  try {
    const [next, old] = await Promise.all([getSnapshot(state.kernel, state.arch), state.compare ? getSnapshot(state.compare, state.arch) : null]);
    if (id !== requestId) return;
    snapshot = next; previous = old;
    renderMetadata(); renderRows();
  } catch (error) {
    if (id !== requestId) return;
    $('error').textContent = `${error.message} ${t('Check that the dataset exists, then reload to retry.')}`;
    $('error').hidden = false;
    $('results').textContent = t("Table unavailable");
  } finally {
    if (id === requestId) $('syscall-table').removeAttribute('aria-busy');
  }
}

function resetSearch() {
  state.query = ''; state.all = false;
  $('search').value = ''; $('show-unimplemented').checked = false;
  renderRows(); saveURL(); $('search').focus();
}
function downloadFile(text, type, filename) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = filename;
  document.body.append(anchor); anchor.click(); anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$('architectures').addEventListener('click', event => {
  const link = event.target.closest('[data-arch]');
  if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  event.preventDefault(); state.arch = link.dataset.arch; state.expanded = ''; refresh();
});
$('kernel').addEventListener('change', () => {
  state.kernel = $('kernel').value;
  if (state.compare === state.kernel) state.compare = '';
  state.expanded = ''; refresh();
});
$('compare').addEventListener('change', () => { state.compare = $('compare').value; refresh(); });
$('search-form').addEventListener('submit', event => event.preventDefault());
$('search').addEventListener('input', () => { state.query = $('search').value; renderRows(); saveURL(); });
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
  const button = event.target.closest('[data-name]');
  if (!button) return;
  const name = button.dataset.name;
  state.expanded = state.expanded === name ? '' : name;
  renderRows(); saveURL();
  // Re-rendering replaces the button; restore keyboard focus on the new node.
  $('rows').querySelector(`[data-name="${CSS.escape(name)}"]`)?.focus({ preventScroll: true });
});
window.addEventListener('zaryob:language', () => {
  if (!manifest) return;
  updateSelects();
  if (snapshot) { renderMetadata(); renderRows(); }
  else $('results').textContent = t('Loading kernel table…');
});
window.addEventListener('hashchange', () => {
  if (!location.hash.startsWith('#sys-')) return;
  state.expanded = decodeURIComponent(location.hash.slice(5)); renderRows();
  document.getElementById(`sys-${state.expanded}`)?.scrollIntoView({ block: 'center' });
});

try {
  manifest = await getJSON(sitePath('data/manifest.json'));
  if (!manifest.architectures.some(a => a.id === state.arch)) state.arch = 'x64';
  if (!manifest.versions.includes(state.kernel)) state.kernel = manifest.latest;
  if (!manifest.versions.includes(state.compare) || state.compare === state.kernel) state.compare = '';
  $('search').value = state.query;
  $('hex').checked = state.hex; $('show-unimplemented').checked = state.all;
  $('convention-rows').innerHTML = manifest.architectures.map(a => `<tr><td><a href="${rootPath}?arch=${a.id}">${esc(a.label)}</a></td><td>${esc(a.instruction)}</td><td>${a.nr}</td><td>${a.result}</td><td>${a.registers.join(', ')}</td></tr>`).join('');
  await refresh();
  if (state.expanded) document.getElementById(`sys-${state.expanded}`)?.scrollIntoView({ block: 'center' });
} catch (error) {
  $('error').textContent = `${error.message} ${t('Check the site deployment and data/manifest.json, then reload to retry.')}`;
  $('error').hidden = false; $('results').textContent = t("Dataset unavailable");
}
