// SPDX-License-Identifier: GPL-2.0-only
// Lookup logic for the errno, signal and ioctl pages. No DOM access: the same
// functions run in the browser and under `node --test`.
const normalize = text => String(text).toLowerCase().normalize('NFD').replace(/\p{M}/gu, '').replace(/ı/g, 'i');

export function parseNumber(value) {
  const text = String(value ?? '').trim().toLowerCase();
  if (!/^(?:0x[\da-f]+|\d+)$/.test(text)) return null;
  const number = Number(text);
  return Number.isSafeInteger(number) ? number : null;
}

// An ioctl request is 32 bits wide; anything else is not a request number.
export function parseRequest(value) {
  const number = parseNumber(value);
  return number !== null && number <= 0xFFFFFFFF ? number : null;
}

export const hex = (number, width = 0) => `0x${number.toString(16).toUpperCase().padStart(width, '0')}`;

export function normalizeArch(document, arch) {
  if (Object.hasOwn(document.architectures, arch)) return arch;
  return Object.hasOwn(document.architectures, 'x64') ? 'x64' : Object.keys(document.architectures)[0];
}

// The table an architecture uses; `key` and `group` name the ioctl variants.
export function archTable(document, arch, key = 'table', group = 'tables') {
  return document[group][document.architectures[arch][key]];
}

// Rows of one architecture, by number; a name defined as another name follows it.
// `elsewhere` lists the other covered architectures that give the name a
// different number, or (number null) do not define it.
export function tableRows(document, arch) {
  const numbers = new Map();
  for (const other of Object.keys(document.architectures)) {
    for (const entry of archTable(document, other).entries) {
      if (!numbers.has(entry.name)) numbers.set(entry.name, new Map());
      numbers.get(entry.name).set(other, entry.number);
    }
  }
  const others = Object.keys(document.architectures).filter(other => other !== arch);
  return archTable(document, arch).entries.map((entry, index) => {
    const groups = new Map();
    for (const other of others) {
      const number = numbers.get(entry.name).get(other) ?? null;
      if (number === entry.number) continue;
      if (!groups.has(number)) groups.set(number, []);
      groups.get(number).push(other);
    }
    return { ...entry, index, elsewhere: [...groups].map(([number, architectures]) => ({ number, architectures })) };
  }).sort((a, b) => a.number - b.number || Boolean(a.alias_of) - Boolean(b.alias_of) || a.index - b.index);
}

export function defaultAction(document, entry) {
  const actions = document.default_actions?.signals ?? {};
  return actions[entry.name] ?? (entry.alias_of ? actions[entry.alias_of] : undefined) ?? null;
}

// `texts` lists the searchable strings of a row; a number matches exactly.
export function searchRows(rows, query = '', texts = row => [row.name, row.alias_of, row.comment], numberOf = row => row.number) {
  const q = normalize(query.trim());
  if (!q) return rows;
  const number = parseNumber(q);
  return rows.filter(row => (number !== null && numberOf(row) === number)
    || texts(row).some(text => text && normalize(text).includes(q)));
}

export const commandTexts = row => [row.name, row.alias_of, row.comment, row.expression, row.source?.path];
export const magicTexts = row => [row.code, hex(row.value, 2), row.sequence, ...row.includes, ...row.comments];

// Fields from the most significant bit down, with the bit positions they occupy.
export function ioctlFields(encoding) {
  return Object.entries(encoding.fields)
    .map(([name, field]) => ({ name, bits: field.bits, shift: field.shift, low: field.shift, high: field.shift + field.bits - 1, source: field.source }))
    .sort((a, b) => b.shift - a.shift);
}

export function decodeIoctl(value, encoding) {
  const field = name => {
    const { bits, shift } = encoding.fields[name];
    // Division keeps every step inside the unsigned 32-bit range.
    return Math.floor(value / 2 ** shift) % 2 ** bits;
  };
  const dir = field('dir');
  const { none, read, write } = encoding.directions;
  const names = [];
  if (dir === none.value || (none.value && dir & none.value)) names.push('none');
  if (dir & read.value) names.push('read');
  if (dir & write.value) names.push('write');
  const type = field('type');
  return {
    value, dir: { value: dir, names }, size: field('size'),
    type: { value: type, character: type >= 0x20 && type <= 0x7E ? String.fromCharCode(type) : null },
    nr: field('nr'),
  };
}

export function matchingCommands(entries, value) {
  return entries.filter(entry => entry.value === value);
}

// Registry rows whose code is this type and whose sequence range holds this number.
export function matchingMagic(rows, type, nr) {
  return rows.filter(row => row.value === type && (!row.range || (row.range[0] <= nr && nr <= row.range[1])));
}

// Upstream snapshots link to the tagged file; a local import links to its bundled copy.
export function sourceURL(document, source, bundled) {
  return document.provenance.kind === 'upstream'
    ? `https://github.com/torvalds/linux/blob/${encodeURIComponent(document.kernel)}/${source.path}${source.line ? `#L${source.line}` : ''}`
    : `${bundled}sources/${source.path}`;
}

// View state lives in the query string, so a view can be linked and restored.
export function readAbiRoute(address) {
  const p = new URL(address).searchParams;
  return { arch: p.get('arch') || 'x64', query: p.get('q') || p.get('highlight') || '', request: p.get('req') || '', magic: p.get('magic') || '' };
}

export function abiURL(address, state) {
  const url = new URL(address);
  const p = new URLSearchParams();
  // x86-64 is the default, so the plain page address stays the canonical one.
  if (state.arch !== 'x64') p.set('arch', state.arch);
  // Keep the explicit language in this history entry, not a stored preference.
  if (url.searchParams.has('lang')) p.set('lang', url.searchParams.get('lang'));
  if (state.query) p.set('q', state.query);
  if (state.request) p.set('req', state.request);
  if (state.magic) p.set('magic', state.magic);
  return `${url.pathname}${p.size ? `?${p}` : ''}${url.hash}`;
}
