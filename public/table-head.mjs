// SPDX-License-Identifier: GPL-2.0-only
// Phones scroll long tables with the page instead of inside their box (see syscall.css);
// keep each table's heading row just under the sticky site header while the table passes beneath it.
const pageScrolledTables = matchMedia('(max-width: 760px), (max-height: 500px)');

export function keepTableHeadsVisible(tables) {
  let frame = 0;
  const place = () => {
    frame = 0;
    const top = document.querySelector('.console-header')?.getBoundingClientRect().bottom ?? 0;
    for (const table of tables) {
      if (!pageScrolledTables.matches || !table.tHead) { table.style.removeProperty('--head-offset'); continue; }
      const box = table.getBoundingClientRect();
      const offset = Math.min(Math.max(top - box.top, 0), Math.max(box.height - table.tHead.offsetHeight, 0));
      table.style.setProperty('--head-offset', `${offset}px`);
    }
  };
  const schedule = () => { frame ||= requestAnimationFrame(place); };
  addEventListener('scroll', schedule, { passive: true });
  addEventListener('resize', schedule);
  pageScrolledTables.addEventListener('change', schedule);
  const observer = new ResizeObserver(schedule);
  for (const table of tables) observer.observe(table);
}
