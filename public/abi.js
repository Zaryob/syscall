// SPDX-License-Identifier: GPL-2.0-only
import {
  abiURL, archTable, commandTexts, decodeIoctl, defaultAction, hex, ioctlFields, magicTexts, matchingCommands,
  matchingMagic, normalizeArch, parseRequest, readAbiRoute, searchRows, sourceURL, tableRows,
} from './abi.mjs';
import { abiCopy } from './abi-copy.mjs';
import { withBase } from './paths.mjs';
import { referenceCopy } from './reference.mjs';
import { keepTableHeadsVisible } from './table-head.mjs';

const { t, apply: applyLanguage } = window.ZaryobI18n;
const $ = id => document.getElementById(id);
const rootPath = document.querySelector('meta[name="site-root"]').content;
const sitePath = path => withBase(rootPath, path);
const page = document.querySelector('[data-abi-page]').dataset.abiPage;
const documents = { errno: ['errno'], signals: ['signals'], ioctl: ['ioctl', 'ioctl-numbers'] }[page];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const copy = () => abiCopy(window.ZaryobI18n.language);
const state = readAbiRoute(location.href);
let manifest, data, registry, release, restoring = false;
keepTableHeadsVisible(document.querySelectorAll('.table-scroll > table'));

async function getJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(t('Could not read {url} (HTTP {status}).', { url, status: response.status }));
  return response.json();
}
const releasePath = file => sitePath(`data/abi/${release}/${file}`);
const sourceLink = source => `<a href="${esc(sourceURL(data, source, releasePath('')))}">${esc(source.path)}${source.line ? `:${source.line}` : ''}</a>`;
const kernelText = text => `<span lang="en">${esc(text)}</span>`;
const labelOf = arch => data.architectures[arch].label;

function saveURL(mode = 'replace') {
  if (restoring) return;
  const url = abiURL(location.href, state);
  if (url !== location.pathname + location.search + location.hash) {
    history[mode === 'push' ? 'pushState' : 'replaceState'](null, '', url);
  }
}

function renderCopy() {
  const text = copy();
  const values = {
    errnoLede: text.errnoLede, signalsLede: text.signalsLede, ioctlLede: text.ioctlLede,
    commandsNote: text.commandsNote, registryNote: text.registryNote, legacy: text.legacy,
    directionHelp: text.directionHelp, regenerate: text.regenerate, regenerateLocal: text.regenerateLocal,
    coverage: release ? text.coverage(release.slice(1)) : '',
    about: data ? text.about(release.slice(1), data.licensing.generator) : '',
  };
  document.querySelectorAll('[data-abi-copy]').forEach(node => {
    const value = values[node.dataset.abiCopy];
    if (typeof value === 'string') node.innerHTML = value;
  });
  const shared = referenceCopy(window.ZaryobI18n.language);
  document.querySelectorAll('[data-syscall-copy]').forEach(node => {
    const value = shared[node.dataset.syscallCopy];
    if (typeof value === 'string') node.innerHTML = value;
  });
}

// Links between the sections keep the selected architecture and an explicit language.
function renderLinks() {
  const language = new URLSearchParams(location.search).get('lang');
  document.querySelectorAll('[data-abi-link]').forEach(link => {
    const url = new URL(link.getAttribute('href'), location.href);
    if (link.dataset.abiLink === 'arch') {
      if (state.arch === 'x64') url.searchParams.delete('arch'); else url.searchParams.set('arch', state.arch);
    }
    if (language) url.searchParams.set('lang', language); else url.searchParams.delete('lang');
    link.href = url.pathname + url.search + url.hash;
  });
}

function headerNote(names) {
  const text = copy();
  const label = esc(labelOf(state.arch));
  return names.map(name => {
    const header = data.architectures[state.arch].headers[name];
    const path = sourceLink({ path: header.path });
    return header.kind === 'architecture'
      ? text.ownHeader(label, name, path)
      : text.genericHeader(label, name, path, header.kind, sourceLink({ path: header.kbuild, line: header.line }));
  }).join(' ');
}

function elsewhereHTML(row) {
  const text = copy();
  if (!row.elsewhere.length) return `<span class="muted" aria-label="${esc(text.sameEverywhere)}">—</span>`;
  return row.elsewhere.map(group => {
    const labels = group.architectures.map(labelOf);
    const who = labels.length > 3 ? `<span title="${esc(labels.join(', '))}">${esc(text.others(labels.length))}</span>` : esc(labels.join(', '));
    return `<span class="abi-difference">${who}: ${group.number === null ? `<span class="muted">${esc(text.absent)}</span>` : `<code>${group.number}</code>`}</span>`;
  }).join('');
}

function nameCell(row) {
  const alias = row.alias_of ? ` <span class="small">${esc(copy().aliasOf(row.alias_of))}</span>` : '';
  return `<th scope="row" id="${esc(row.name)}"><code>${esc(row.name)}</code>${alias}</th>`;
}
const commentCell = row => `<td>${row.comment ? kernelText(row.comment) : `<span class="muted" aria-label="${esc(copy().noComment)}">—</span>`}</td>`;

function setResults(count, total) {
  $('results').textContent = t('{count} of {total} entries', { count, total });
  $('empty').hidden = count > 0;
}

function renderErrno() {
  const rows = tableRows(data, state.arch);
  const visible = searchRows(rows, state.query);
  $('rows').innerHTML = visible.map(row => `<tr><td class="abi-number">${row.number}</td>${nameCell(row)}${commentCell(row)}
    <td>${elsewhereHTML(row)}</td><td class="abi-source">${sourceLink(row.source)}</td></tr>`).join('');
  setResults(visible.length, rows.length);
  $('arch-note').innerHTML = headerNote(['errno.h']);
}

function actionHTML(action) {
  const text = copy();
  if (!action) return `<span class="muted">${esc(text.noAction)}</span>`;
  return `${esc(text.actions[action.action] ?? action.action)}${action.markers.map(marker => ` <a href="#action-note-${marker === '+' ? 'always' : 'job-control'}">(${esc(marker)})</a>`).join('')}`;
}

function renderSignals() {
  const text = copy();
  const rows = tableRows(data, state.arch);
  const visible = searchRows(rows, state.query, row => [row.name, row.alias_of, row.comment, defaultAction(data, row)?.action]);
  $('rows').innerHTML = visible.map(row => `<tr><td class="abi-number">${row.number}</td>${nameCell(row)}<td>${actionHTML(defaultAction(data, row))}</td>
    ${commentCell(row)}<td>${elsewhereHTML(row)}</td><td class="abi-source">${sourceLink(row.source)}</td></tr>`).join('');
  setResults(visible.length, rows.length);
  $('arch-note').innerHTML = headerNote(['signal.h']);
  const { realtime } = archTable(data, state.arch);
  const actions = data.default_actions;
  const range = realtime.max.value === null ? text.realtimeUnresolved(realtime.min.value, esc(realtime.max.expression)) : text.realtime(realtime.min.value, realtime.max.value);
  $('realtime').innerHTML = `${range} ${esc(text.realtimeAction(text.actions[actions.realtime.action] ?? actions.realtime.action))} ${sourceLink(realtime.min.source)}`;
  $('action-legend').innerHTML = `<p>${esc(text.actionLegend)}</p><dl class="api-list">${Object.entries(actions.definitions).map(([name, definition]) =>
    `<dt>${esc(text.actions[name] ?? name)} · <code>${esc(name)}</code></dt><dd>${kernelText(definition)}</dd>`).join('')}</dl>
    ${Object.entries(actions.notes).map(([marker, note]) => `<p class="small" id="action-note-${marker === '+' ? 'always' : 'job-control'}">(${esc(marker)}) ${kernelText(note)}</p>`).join('')}
    <p class="small">${esc(text.actionSource)} ${sourceLink(actions.source)}.</p>`;
}

function directionText(names) {
  const text = copy();
  return names.length ? names.map(name => text.directions[name]).join(' + ') : text.noDirection;
}

function renderLayout() {
  const text = copy();
  const encoding = archTable(data, state.arch, 'encoding', 'encodings');
  const fields = ioctlFields(encoding);
  const labels = { dir: t('Direction'), size: t('Size'), type: t('Type'), nr: t('Sequence number') };
  $('layout-intro').innerHTML = `${esc(text.layoutIntro(labelOf(state.arch), Object.fromEntries(fields.map(field => [field.name, field.bits]))))} ${headerNote(['ioctl.h'])}`;
  $('bit-layout').innerHTML = fields.map(field => `<div style="--bits:${field.bits}"><strong>${esc(labels[field.name])}</strong><span>${esc(text.bitRange(field.high, field.low))}</span></div>`).join('');
  $('layout-rows').innerHTML = fields.map(field => `<tr><th scope="row">${esc(labels[field.name])} <code>${esc(field.name)}</code></th><td class="abi-number">${field.bits}</td>
    <td>${esc(text.bitRange(field.high, field.low))}</td><td class="abi-source">${sourceLink(field.source)}</td></tr>`).join('');
  $('direction-values').innerHTML = `${esc(text.directionValues)} ${['none', 'write', 'read'].map(name =>
    `<code>_IOC_${name.toUpperCase()}</code> = ${encoding.directions[name].value} (${esc(text.directions[name])})`).join(' · ')}. ${esc(text.directionHelp)}`;
}

function commandValue(row) {
  const text = copy();
  if (row.value === null) {
    return `<span class="muted">${esc(row.size_type && row.size === null ? text.sizeDepends(row.size_type) : text.valueDepends)}</span>`;
  }
  const value = hex(row.value);
  return `<button type="button" class="text-button" data-request="${value}" aria-label="${esc(text.decodeValue(`${row.name} ${value}`))}"><code>${value}</code></button>`;
}
const commandEncoding = row => row.alias_of ? `<code>${esc(row.alias_of)}</code>` : row.expression ? `<code>${esc(row.expression)}</code>` : '<span class="muted">—</span>';

function renderCommands() {
  const rows = archTable(data, state.arch, 'commands', 'commands').entries;
  const visible = searchRows(rows, state.query, commandTexts, row => row.value);
  const sets = copy().sets;
  $('rows').innerHTML = visible.map(row => `<tr>${nameCell(row)}<td class="abi-number">${commandValue(row)}</td><td>${commandEncoding(row)}</td>
    <td>${esc(sets[row.set] ?? row.set)}</td>${commentCell(row)}<td class="abi-source">${sourceLink(row.source)}</td></tr>`).join('');
  setResults(visible.length, rows.length);
}

function renderRegistry() {
  const visible = searchRows(registry.rows, state.magic, magicTexts, row => row.value);
  $('magic-rows').innerHTML = visible.map(row => `<tr><th scope="row"><code>${esc(row.code)}</code></th><td class="abi-number"><code>${esc(row.sequence)}</code></td>
    <td>${row.includes.map(esc).join('<br>')}</td><td>${row.comments.map(kernelText).join('<br>')}</td></tr>`).join('');
  $('magic-results').textContent = t('{count} of {total} entries', { count: visible.length, total: registry.rows.length });
  $('magic-empty').hidden = visible.length > 0;
  $('registry-source').innerHTML = sourceLink(registry.source);
}

function renderDecoder() {
  const text = copy();
  const output = $('decoder-result');
  const input = state.request.trim();
  $('request').setAttribute('aria-invalid', 'false');
  if (!input) { output.innerHTML = `<p class="muted">${esc(text.decodePrompt)}</p>`; return; }
  const value = parseRequest(input);
  if (value === null) {
    $('request').setAttribute('aria-invalid', 'true');
    output.innerHTML = `<p class="error">${esc(text.invalidRequest)}</p>`;
    return;
  }
  const decoded = decodeIoctl(value, archTable(data, state.arch, 'encoding', 'encodings'));
  const commands = matchingCommands(archTable(data, state.arch, 'commands', 'commands').entries, value);
  const magic = matchingMagic(registry.rows, decoded.type.value, decoded.nr);
  const type = `${hex(decoded.type.value, 2)}${decoded.type.character ? ` <code>'${esc(decoded.type.character)}'</code>` : ''}`;
  output.innerHTML = `<h3>${esc(text.decoded(`${hex(value, 8)} (${value})`))} · ${esc(labelOf(state.arch))}</h3>
    <dl class="decoded">
      <dt>${esc(t('Direction'))}</dt><dd><code>${decoded.dir.value}</code> · ${esc(directionText(decoded.dir.names))}</dd>
      <dt>${esc(t('Size'))}</dt><dd><code>${decoded.size}</code> · ${esc(text.bytes(decoded.size))}</dd>
      <dt>${esc(t('Type'))}</dt><dd>${type}</dd>
      <dt>${esc(t('Sequence number'))}</dt><dd>${hex(decoded.nr, 2)} · ${decoded.nr}</dd>
    </dl>
    <h4>${esc(t('Matching commands'))}</h4>
    ${commands.length ? `<ul>${commands.map(row => `<li><a href="#${esc(row.name)}"><code>${esc(row.name)}</code></a>${row.expression ? ` · <code>${esc(row.expression)}</code>` : ''} · ${sourceLink(row.source)}</li>`).join('')}</ul>` : `<p class="muted">${esc(text.noCommandMatch)}</p>`}
    <h4>${esc(t('Registered magic numbers'))}</h4>
    ${magic.length ? `<ul>${magic.map(row => `<li><code>${esc(row.code)}</code> <code>${esc(row.sequence)}</code> · ${row.includes.map(esc).join(', ') || '—'}${row.comments.length ? ` · ${kernelText(row.comments.join(' '))}` : ''}</li>`).join('')}</ul>` : `<p class="muted">${esc(text.noMagicMatch)}</p>`}`;
}

function render() {
  const text = copy();
  document.title = `${text.titles[page]} · ${labelOf(state.arch)} · Linux ${release.slice(1)} · ${t('System Call Reference')}`;
  renderCopy();
  renderLinks();
  if (page === 'errno') renderErrno();
  if (page === 'signals') renderSignals();
  if (page === 'ioctl') { renderLayout(); renderDecoder(); renderCommands(); renderRegistry(); }
  applyLanguage($('main'));
}

function restoreControls() {
  $('search').value = state.query;
  $('architecture-picker').value = state.arch;
  if (page === 'ioctl') { $('request').value = state.request; $('magic-search').value = state.magic; }
}

function resetSearch() {
  state.query = '';
  $('search').value = '';
  render(); saveURL(); $('search').focus();
}

$('search-form').addEventListener('submit', event => event.preventDefault());
$('search').addEventListener('input', () => { state.query = $('search').value; if (data) render(); saveURL(); });
$('clear').addEventListener('click', resetSearch);
$('reset-search').addEventListener('click', resetSearch);
$('architecture-picker').addEventListener('change', () => { state.arch = $('architecture-picker').value; render(); saveURL('push'); });
if (page === 'ioctl') {
  $('decoder-form').addEventListener('submit', event => {
    event.preventDefault();
    state.request = $('request').value.trim();
    renderDecoder(); saveURL('push');
  });
  $('magic-form').addEventListener('submit', event => event.preventDefault());
  $('magic-search').addEventListener('input', () => { state.magic = $('magic-search').value; if (data) renderRegistry(); saveURL(); });
  $('magic-reset').addEventListener('click', () => { state.magic = ''; $('magic-search').value = ''; renderRegistry(); saveURL(); $('magic-search').focus(); });
  $('rows').addEventListener('click', event => {
    const button = event.target.closest('[data-request]');
    if (!button) return;
    state.request = button.dataset.request;
    $('request').value = state.request;
    renderDecoder(); saveURL('push');
    $('decoder').scrollIntoView({ block: 'start' });
    $('decoder-result').focus({ preventScroll: true });
  });
}
window.addEventListener('zaryob:language', () => { if (data && !restoring) render(); else renderCopy(); });
window.addEventListener('popstate', () => {
  if (!data) return;
  restoring = true;
  try {
    const requested = new URLSearchParams(location.search).get('lang');
    const language = window.ZaryobLanguage.supported.includes(requested) ? requested : document.documentElement.lang;
    window.ZaryobLanguage.set(language, { persist: false, updateUrl: false });
    Object.assign(state, readAbiRoute(location.href));
    state.arch = normalizeArch(data, state.arch);
    restoreControls();
  } finally {
    restoring = false;
  }
  render();
});

renderCopy();
renderLinks();
try {
  manifest = await getJSON(sitePath('data/abi/manifest.json'));
  release = manifest.latest;
  const loaded = await Promise.all(documents.map(name => getJSON(releasePath(`${name}.json`))));
  for (const document of loaded) {
    if (document?.kernel !== release) throw new Error(t('Invalid kernel table at {url}.', { url: releasePath('') }));
  }
  [data, registry] = loaded;
  state.arch = normalizeArch(data, state.arch);
  $('architecture-picker').replaceChildren(...manifest.architectures.filter(arch => Object.hasOwn(data.architectures, arch.id)).map(
    arch => new Option(arch.label, arch.id, false, arch.id === state.arch)));
  $('architecture-picker').disabled = false;
  $('download').href = releasePath(`${documents[0]}.json`);
  $('download').download = `linux-${release}-${documents[0]}.json`;
  $('download').hidden = false;
  $('abi-sources').href = releasePath('sources.json');
  restoreControls();
  render();
  saveURL();
  // Rows are rendered after the browser first looked for the fragment.
  if (location.hash.length > 1) document.getElementById(location.hash.slice(1))?.scrollIntoView({ block: 'center' });
} catch (error) {
  $('error').textContent = `${error.message} ${copy().loadError}`;
  $('error').hidden = false;
  $('results').textContent = t('Dataset unavailable');
}
