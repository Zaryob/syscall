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

// Fragments stop just below the sticky site header (static-pages.css); the shared theme (console/theme.js) measures
// its height into --console-header-height, following text size, wrapping and width.

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
  const scroller = rangeBar.querySelector('.static-ranges-scroll');
  const rangeLinks = [...rangeBar.querySelectorAll('ul a')];
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
  // On a narrow screen the ranges scroll sideways: fade the edge that hides some, and keep the range of the target
  // row, or of the rows under the bar, in view.
  const fade = () => {
    const hidden = scroller.scrollWidth - scroller.clientWidth;
    rangeBar.style.setProperty('--ranges-start', `${scroller.offsetLeft}px`);
    rangeBar.style.setProperty('--ranges-end', `${rangeBar.clientWidth - scroller.offsetLeft - scroller.clientWidth}px`);
    rangeBar.classList.toggle('static-ranges--fade-start', hidden > 1 && scroller.scrollLeft > 1);
    rangeBar.classList.toggle('static-ranges--fade-end', hidden > 1 && scroller.scrollLeft < hidden - 1);
  };
  const startOf = link => document.getElementById(link.hash.slice(1));
  let shownRange = null;
  const showRange = link => {
    shownRange = link;
    if (!link) return;
    const box = scroller.getBoundingClientRect();
    const item = link.getBoundingClientRect();
    const edge = Math.min(40, Math.max(16, rangeBar.clientWidth * 0.08));
    if (item.left < box.left + edge) scroller.scrollLeft -= box.left + edge - item.left;
    else if (item.right > box.right - edge) scroller.scrollLeft += item.right - box.right + edge;
  };
  const rangeOf = row => rangeLinks.findLast(link => {
    const start = startOf(link);
    return start && (start === row || start.compareDocumentPosition(row) & Node.DOCUMENT_POSITION_FOLLOWING);
  });
  const showTarget = () => {
    const row = document.getElementById(decodeURIComponent(location.hash.slice(1)))?.closest('.static-calls tr');
    if (row) showRange(rangeOf(row));
  };
  let spying = false;
  const spy = () => {
    spying = false;
    // A fragment lands a few pixels below the bar; that row counts as under it.
    const line = rangeBar.getBoundingClientRect().bottom + 16;
    const current = rangeLinks.findLast(link => { const start = startOf(link); return start && !start.hidden && start.getBoundingClientRect().top <= line; }) ?? rangeLinks[0];
    if (current !== shownRange) showRange(current);
  };
  scroller.addEventListener('scroll', fade, { passive: true });
  addEventListener('scroll', () => { if (!spying) { spying = true; requestAnimationFrame(spy); } }, { passive: true });
  addEventListener('hashchange', () => {
    const target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (target?.closest('tr[hidden]')) { clearFilter(); target.scrollIntoView(); }
    showTarget();
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
    // A new text size or width moves the ranges; keep the shown one in view.
    showRange(shownRange);
    fade();
  };
  place();
  showTarget();
  addEventListener('resize', place);
  new ResizeObserver(place).observe(rangeBar);
}
