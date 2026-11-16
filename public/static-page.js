// SPDX-License-Identifier: GPL-2.0-only
// Generated pages are plain HTML in one language each (scripts/static_pages.py).
// The header's language selector opens the translation through the page's
// data-translation-lang link (console/i18n.js); this only keeps the footer notice
// in the interface language.
import { referenceCopy } from './reference.mjs';

function renderCopy() {
  const copy = referenceCopy(window.ZaryobLanguage.language);
  document.querySelectorAll('[data-syscall-copy]').forEach(node => { node.innerHTML = copy[node.dataset.syscallCopy] ?? node.innerHTML; });
}
renderCopy();
window.ZaryobLanguage.subscribe(renderCopy);

// Architecture pages (scripts/static_pages.py): the number-range bar is plain links and stays sticky under the site
// header; this reveals the row filter above it. Both stay in view while they take at most 15% of the window height;
// otherwise the filter scrolls with the page and a link in the bar brings it back.
const filterForm = document.querySelector('form.static-filter');
const rangeBar = document.querySelector('.static-ranges');
if (filterForm && rangeBar) {
  const root = document.documentElement;
  const input = filterForm.querySelector('input');
  const status = filterForm.querySelector('[role=status]');
  const searchLink = rangeBar.querySelector('.static-filter-link');
  const rows = [...document.querySelectorAll('.static-calls tbody tr')];
  const keys = rows.map(row => {
    const [number, hex] = row.querySelectorAll('.abi-number');
    return { number: number.textContent, hex: hex.textContent.toLowerCase(), name: row.querySelector('th code').textContent.toLowerCase() };
  });
  const filter = () => {
    const query = input.value.trim().toLowerCase();
    let shown = 0;
    rows.forEach((row, i) => {
      const { number, hex, name } = keys[i];
      row.hidden = Boolean(query) && !(name.includes(query) || number.startsWith(query) || (query.startsWith('0x') && hex.startsWith(query)));
      if (!row.hidden) shown++;
    });
    status.textContent = query ? filterForm.dataset.count.replace('{shown}', shown).replace('{total}', rows.length) : '';
  };
  const clearFilter = () => { if (input.value) { input.value = ''; filter(); } };
  filterForm.hidden = false;
  input.addEventListener('input', filter);
  filterForm.addEventListener('submit', event => {
    event.preventDefault();
    input.blur();
    rows.find(row => !row.hidden)?.querySelector('a')?.focus();
  });
  // A range or name fragment must not point at a row the filter hides.
  rangeBar.querySelector('ul').addEventListener('click', event => { if (event.target.closest('a')) clearFilter(); });
  addEventListener('hashchange', () => {
    const target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (target?.closest('tr[hidden]')) { clearFilter(); target.scrollIntoView(); }
  });
  searchLink.addEventListener('click', event => {
    event.preventDefault();
    filterForm.scrollIntoView({ block: 'center' });
    input.focus({ preventScroll: true });
  });
  // Sticky offsets follow the real header and bar heights, which change with the text size.
  const place = () => {
    root.classList.add('static-jump-ready');
    root.style.setProperty('--static-header', `${document.querySelector('.console-header')?.offsetHeight ?? 0}px`);
    const both = filterForm.offsetHeight + rangeBar.offsetHeight <= innerHeight * 0.15;
    root.classList.toggle('static-filter-sticky', both);
    root.style.setProperty('--static-filter', both ? `${filterForm.offsetHeight}px` : '0px');
    root.style.setProperty('--static-ranges', `${rangeBar.offsetHeight}px`);
    searchLink.hidden = both;
  };
  place();
  addEventListener('resize', place);
  new ResizeObserver(place).observe(rangeBar);
}
