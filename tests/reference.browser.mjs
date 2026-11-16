// SPDX-License-Identifier: GPL-2.0-only
import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const site = new URL('../_site-test/', import.meta.url);
const base = 'http://localhost/syscall-test/';

async function openPage(t, options = {}) {
  const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined });
  t.after(() => browser.close());
  const context = await browser.newContext({ permissions: ['clipboard-read', 'clipboard-write'], ...options });
  const page = await context.newPage();
  page.setDefaultTimeout(5000);
  await page.route('https://cloud.umami.is/**', route => route.abort());
  await page.route('https://www.googletagmanager.com/**', route => route.abort());
  await page.route(`${base}**`, route => {
    const pathname = new URL(route.request().url()).pathname.slice(new URL(base).pathname.length);
    // A directory address is its index document, as on the static host.
    return route.fulfill({ path: fileURLToPath(new URL(pathname.replace(/(^|\/)$/, '$1index.html'), site)) });
  });
  return page;
}

test('same-named comparison rows toggle independently and retain their identities', async t => {
  const page = await openPage(t);
  const comparisonURL = `${base}?arch=x86&kernel=v7.3&compare=v1.0&q=chown&lang=en`;
  await page.goto(comparisonURL);
  const current = page.locator('[data-call="v7.3:182:chown"]');
  const removed = page.locator('[data-call="v1.0:16:chown"]');
  const details = page.locator('.detail-row');
  await current.evaluate(button => { button.dataset.originalNode = 'yes'; });

  await current.focus();
  await page.keyboard.press('Enter');
  assert.equal(await current.getAttribute('aria-expanded'), 'true');
  assert.equal(await removed.getAttribute('aria-expanded'), 'false');
  assert.equal(await details.count(), 1);
  assert.equal(await current.evaluate(button => document.activeElement === button), true);

  await removed.focus();
  await page.keyboard.press('Space');
  assert.equal(await current.getAttribute('aria-expanded'), 'false');
  assert.equal(await removed.getAttribute('aria-expanded'), 'true');
  assert.equal(await current.getAttribute('data-original-node'), 'yes');
  assert.equal(await removed.evaluate(button => document.activeElement === button), true);
  assert.equal(await details.count(), 1);
  assert.equal(await details.getAttribute('id'), await removed.getAttribute('aria-controls'));
  assert.equal(decodeURIComponent(new URL(page.url()).hash), '#sys-v1.0:16:chown');
  const permalink = await details.getByRole('link', { name: 'Permanent link' }).getAttribute('href');

  await page.reload();
  await details.waitFor();
  assert.equal(await removed.getAttribute('aria-expanded'), 'true');
  await page.goto(new URL(permalink, base).href);
  await details.waitFor();
  assert.equal(await removed.getAttribute('aria-expanded'), 'true');

  await page.goto(comparisonURL + '#sys-chown');
  await details.waitFor();
  assert.equal(await current.getAttribute('aria-expanded'), 'true');
  assert.equal(await removed.getAttribute('aria-expanded'), 'false');
});

test('the copied C declaration matches the historical source', async t => {
  const page = await openPage(t);
  await page.goto(`${base}?arch=x64&kernel=v2.6.12&q=read&lang=en#sys-read`);
  const declaration = 'asmlinkage ssize_t sys_read(unsigned int fd, char __user *buf, size_t count);';
  const signature = page.locator('.detail-row .signature');
  assert.equal(await signature.locator('code').textContent(), declaration);
  await signature.getByRole('button', { name: 'Copy C declaration' }).click();
  await signature.getByRole('status').filter({ hasText: 'Copied' }).waitFor({ state: 'attached' });
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), declaration);
});

test('the ENOSYS note appears only where a release defines no implementation for the ABI', async t => {
  const page = await openPage(t);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const detail = page.locator('.detail-row');
  await page.goto(`${base}?arch=arm&kernel=v7.3&q=uselib&lang=en#sys-uselib`);
  await detail.waitFor();
  assert.match(await detail.textContent(), /define no implementation of this entry point for this ABI.*kernel\/sys_ni\.c:\d+/s);
  await page.goto(`${base}?arch=arm&kernel=v6.6&q=uselib&lang=en#sys-uselib`);
  await detail.waitFor();
  assert.doesNotMatch(await detail.textContent(), /ENOSYS fallback/);
  await page.goto(`${base}?arch=x64&kernel=v7.3&q=io_setup&lang=en#sys-io_setup`);
  await detail.waitFor();
  assert.doesNotMatch(await detail.textContent(), /ENOSYS fallback/);
  assert.match(await page.locator('[data-syscall-copy="availability"]').textContent(), /return ENOSYS when the matching configuration option/);
  await page.goto(`${base}?arch=x86&kernel=v7.3&q=pread64&lang=en#sys-pread64`);
  await detail.waitFor();
  assert.match(await detail.textContent(), /sys_ia32_pread64\(unsigned int fd, char __user \*ubuf/);
  assert.deepEqual(errors, []);
});

test('MIPS common calls are searchable and missing manuals have an explicit bilingual state', async t => {
  const page = await openPage(t);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`${base}?arch=mips-n64&kernel=v7.3&q=set_mempolicy_home_node&lang=en#sys-set_mempolicy_home_node`);
  const detail = page.locator('.detail-row');
  await detail.waitFor();
  assert.match(await detail.textContent(), /5450/);
  await detail.getByText('No manual link is available for this entry.', { exact: true }).waitFor();
  assert.equal(await detail.getByRole('link', { name: /^Read / }).count(), 0);
  await page.locator('[data-console-language]').selectOption('tr');
  await detail.getByText('Bu girdi için man sayfası bağlantısı yok.', { exact: true }).waitFor();
  assert.deepEqual(errors, []);
});

test('PowerPC details expose the architecture declaration and its source', async t => {
  const page = await openPage(t);
  await page.goto(`${base}?arch=ppc&kernel=v7.3&q=mmap&lang=en#sys-mmap`);
  const detail = page.locator('.detail-row');
  await detail.waitFor();
  assert.match(await detail.locator('.signature code').textContent(), /^long sys_mmap\(/);
  assert.equal(await detail.locator('.argument-table tbody tr').count(), 6);
  const source = detail.getByRole('link', { name: 'arch/powerpc/include/asm/syscalls.h:55', exact: true });
  assert.match(await source.getAttribute('href'), /syscalls\.h#L55$/);
});

test('time64 aliases link to an existing base manual', async t => {
  const page = await openPage(t);
  await page.goto(`${base}?arch=x86&kernel=v7.3&q=clock_gettime64&lang=en#sys-clock_gettime64`);
  const link = page.locator('.detail-row').getByRole('link', { name: 'Read clock_gettime(2)', exact: true });
  await link.waitFor();
  assert.equal(await link.getAttribute('href'), 'https://man7.org/linux/man-pages/man2/clock_gettime.2.html');
});

test('the no-JavaScript download follows the active revision under a project baseurl', async t => {
  const page = await openPage(t, { javaScriptEnabled: false });
  await page.goto(base);
  const url = await page.locator('noscript a').getAttribute('href');
  assert.match(url, /^\/syscall-test\/data\/revisions\/v7\.3\/[^/]+\/x64\.json$/);
});

const ready = page => page.waitForFunction(() => document.querySelector('#rows .syscall-row') && !document.querySelector('#syscall-table').hasAttribute('aria-busy'));
const selection = page => page.evaluate(() => ({
  arch: document.querySelector('#architecture-picker').value,
  kernel: document.querySelector('#kernel').value,
  compare: document.querySelector('#compare').value,
  query: document.querySelector('#search').value,
  view: document.querySelector('#syscall-table').dataset.view,
  hex: document.querySelector('#hex').checked,
  all: document.querySelector('#show-unimplemented').checked,
  lang: document.documentElement.lang,
}));

test('real Back/Forward restores selections, typed searches, language, flags and details', async t => {
  const page = await openPage(t);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`${base}?arch=x64&kernel=v7.3&q=write&lang=tr&view=args&hex=1&all=1`);
  await ready(page);
  const first = await selection(page);
  await page.locator('#architecture-picker').selectOption('arm64');
  await ready(page);
  const architecture = await selection(page);
  await page.locator('#kernel').selectOption('v6.12');
  await ready(page);
  const release = await selection(page);
  await page.locator('#compare').selectOption('v6.6');
  await page.locator('#diff-note').waitFor({state:'visible'});
  const length = await page.evaluate(() => history.length);
  await page.locator('#search').fill('read');
  assert.equal(await page.evaluate(() => history.length), length, 'typing replaces, not pushes');
  await page.locator('[data-console-language]').selectOption('en');
  const comparison = await selection(page);
  await page.locator('[data-call="v6.12:63:read"]').click();
  await page.locator('.detail-row').waitFor();
  const detailURL = page.url();
  await page.goBack();
  await ready(page);
  assert.deepEqual(await selection(page), comparison);
  assert.equal(await page.locator('.detail-row').count(), 0);
  await page.goBack();
  await ready(page);
  assert.deepEqual(await selection(page), release);
  await page.goBack();
  await ready(page);
  assert.deepEqual(await selection(page), architecture);
  await page.goBack();
  await ready(page);
  assert.deepEqual(await selection(page), first);
  for (const expected of [architecture, release, comparison]) {
    await page.goForward();
    await ready(page);
    assert.deepEqual(await selection(page), expected);
  }
  await page.goForward();
  await page.locator('.detail-row').waitFor();
  assert.equal(page.url(), detailURL);
  assert.equal(await page.locator('[data-call="v6.12:63:read"]').getAttribute('aria-expanded'), 'true');
  assert.deepEqual(errors, []);
});

test('Back/Forward distinguishes current and removed same-named details', async t => {
  const page = await openPage(t);
  await page.goto(`${base}?arch=x86&kernel=v7.3&compare=v1.0&q=chown&lang=en`);
  await page.locator('#diff-note').waitFor({state:'visible'});
  const current = page.locator('[data-call="v7.3:182:chown"]');
  const removed = page.locator('[data-call="v1.0:16:chown"]');
  await current.click();
  await removed.click();
  await page.goBack();
  await page.locator('[id="detail-v7.3:182:chown"]').waitFor();
  assert.equal(await current.getAttribute('aria-expanded'), 'true');
  await page.goForward();
  await page.locator('[id="detail-v1.0:16:chown"]').waitFor();
  assert.equal(await removed.getAttribute('aria-expanded'), 'true');
});

test('late primary loads cannot overwrite a newer architecture or a history restoration', async t => {
  const page = await openPage(t);
  await page.goto(`${base}?arch=x64&kernel=v6.12&lang=en`);
  await ready(page);
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  let started;
  const intercepted = new Promise(resolve => { started = resolve; });
  await page.route('**/x86.json', async route => {
    started();
    await gate;
    const pathname = new URL(route.request().url()).pathname.slice(new URL(base).pathname.length);
    await route.fulfill({path:fileURLToPath(new URL(pathname, site))});
  });
  await page.locator('#architecture-picker').selectOption('x86');
  await intercepted;
  await page.locator('#architecture-picker').selectOption('arm64');
  await ready(page);
  // Back selects the still-loading x86 entry, then Back restores cached x64.
  await page.goBack();
  await page.goBack();
  await ready(page);
  const received = page.waitForResponse(response => response.url().endsWith('/x86.json'));
  release();
  await (await received).finished();
  await page.waitForLoadState('networkidle');
  await page.waitForFunction(() => document.querySelector('#table-title').textContent.includes('x86-64'));
  assert.equal((await selection(page)).arch, 'x64');
  assert.match(await page.locator('#download').getAttribute('href'), /x64\.json$/);
  assert.equal(new URL(page.url()).searchParams.get('arch'), 'x64');
});

test('late comparison results cannot replace a new comparison', async t => {
  const page = await openPage(t);
  await page.goto(`${base}?arch=x64&kernel=v7.3&lang=en`);
  await ready(page);
  let release, started;
  const gate = new Promise(resolve => { release = resolve; });
  const intercepted = new Promise(resolve => { started = resolve; });
  await page.route('**/data/**/x64.json', async route => {
    if (!route.request().url().includes('/v6.6/')) return route.fallback();
    started(); await gate;
    const pathname = new URL(route.request().url()).pathname.slice(new URL(base).pathname.length);
    await route.fulfill({path:fileURLToPath(new URL(pathname, site))});
  });
  await page.locator('#advanced-options > summary').click();
  await page.locator('#compare').selectOption('v6.6');
  await intercepted;
  await page.locator('#compare').selectOption('v6.12');
  await page.locator('#diff-note').waitFor({state:'visible'});
  const received = page.waitForResponse(response => response.url().includes('/v6.6/'));
  release();
  await (await received).finished();
  await page.waitForLoadState('networkidle');
  assert.equal((await selection(page)).compare, 'v6.12');
  assert.match(await page.locator('#diff-note').textContent(), /Compared with Linux 6\.12/);
});

test('a single-release ABI explains its disabled comparison in both languages', async t => {
  const page = await openPage(t);
  const manifest = JSON.parse(await readFile(new URL('data/manifest.json', site)));
  manifest.versions = [manifest.latest];
  await page.route(`${base}data/manifest.json`, route => route.fulfill({json:manifest}));
  await page.goto(`${base}?arch=x64&lang=en`);
  await ready(page);
  assert.equal(await page.locator('#compare').isDisabled(), true);
  assert.equal(await page.locator('#compare').getAttribute('aria-describedby'), 'compare-help');
  assert.match(await page.locator('#compare-help').textContent(), /at least two/);
  await page.locator('#advanced-options > summary').click();
  assert.equal(await page.locator('#compare-help').isVisible(), true);
  await page.locator('[data-console-language]').selectOption('tr');
  assert.match(await page.locator('#compare-help').textContent(), /en az iki/);
});

test('ABI notes, LTS labels and analytics render in TR/EN without mobile page overflow', async t => {
  const page = await openPage(t, {viewport:{width:390,height:844}});
  await page.goto(`${base}?lang=en#conventions`);
  const rows = page.locator('#convention-rows tr');
  await rows.first().waitFor();
  assert.equal(await rows.count(), 12);
  assert.match(await rows.filter({hasText:'PowerPC 32'}).textContent(), /cr0.SO/);
  assert.match(await rows.filter({hasText:'MIPS n64'}).textContent(), /v1/);
  assert.match(await rows.filter({hasText:'x86-64'}).textContent(), /rdx.*rcx, r11/);
  assert.match(await page.locator('#conventions [data-syscall-copy="abiNotes"]').textContent(), /PPC_FEATURE2_SCV/);
  assert.equal(await page.locator('#conventions th[data-syscall-copy="clobber"]').textContent(), 'Clobber');
  assert.match(await page.locator('footer').textContent(), /visit analytics/);
  await page.locator('[data-console-menu]').click();
  await page.locator('[data-console-language]').selectOption('tr');
  await page.locator('[data-console-menu]').click();
  assert.match(await page.locator('#conventions [data-syscall-copy="abiNotes"]').textContent(), /alt 32/);
  assert.equal(await page.locator('#conventions th[data-syscall-copy="clobber"]').textContent(), 'Bozulan');
  assert.match(await page.locator('footer').textContent(), /ziyaret analitiği/);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await page.goto(`${base}?arch=x64&lang=tr`);
  await ready(page);
  assert.equal(await page.locator('#kernel option').filter({hasText:'LTS'}).count(), 3);
  assert.match(await page.locator('#release-help').textContent(), /7 Kasım 2026/);
  assert.match(await page.locator('#convention-strip').textContent(), /DÖNÜŞ2.*Bozulan/);
});

test('the single argument table keeps filters and data consistent through history', async t => {
  const page = await openPage(t);
  await page.goto(`${base}?arch=x64&kernel=v7.3&q=read&lang=en&view=summary`);
  await ready(page);
  assert.equal(await page.locator('#table-views').count(), 0);
  assert.equal(await page.locator('.summary-heading').count(), 0);
  assert.equal(await page.locator('#syscall-table thead th').count(), 8);
  assert.equal((await selection(page)).view, 'args');
  assert.equal(new URL(page.url()).searchParams.has('view'), false);
  await page.locator('#advanced-options > summary').click();
  await page.locator('#hex').check();
  await page.locator('#show-unimplemented').check();
  await page.goBack(); await ready(page);
  assert.equal((await selection(page)).all, false);
  assert.equal((await selection(page)).hex, true);
  assert.match(await page.locator('.call-number').first().textContent(), /^0x/);
  await page.goBack(); await ready(page);
  assert.equal((await selection(page)).hex, false);
  assert.equal((await selection(page)).view, 'args');
  assert.doesNotMatch(await page.locator('.call-number').first().textContent(), /^0x/);
  await page.goForward(); await ready(page);
  assert.equal((await selection(page)).view, 'args');
});

test('same-document library navigation and social metadata keep working', async t => {
  const page = await openPage(t);
  await page.goto(`${base}?arch=arm64&kernel=v6.12&q=read&lang=tr`);
  await ready(page);
  await page.evaluate(() => { location.hash = '#conventions'; });
  await page.locator('#library').waitFor({state:'visible'});
  assert.equal(await page.locator('#reference').isVisible(), false);
  await page.goBack(); await ready(page);
  assert.equal(await page.locator('#reference').isVisible(), true);
  assert.equal((await selection(page)).arch, 'arm64');
  assert.equal((await selection(page)).query, 'read');
  assert.equal(await page.locator('meta[name="twitter:card"]').getAttribute('content'), 'summary_large_image');
  const imageURL = await page.locator('meta[property="og:image"]').getAttribute('content');
  assert.equal(imageURL, 'https://zaryob.github.io/syscall/assets/syscall-social.png');
  await page.goto(`${base}assets/syscall-social.png`);
  assert.deepEqual(await page.locator('img').evaluate(image => [image.naturalWidth,image.naturalHeight]), [1200,630]);
});

test('a removed detail fragment survives hash navigation while comparison data is still pending', {timeout:15000}, async t => {
  const page = await openPage(t);
  let release, started;
  const gate = new Promise(resolve => { release = resolve; });
  const intercepted = new Promise(resolve => { started = resolve; });
  await page.route('**/v1.0/**/x86.json', async route => {
    started(); await gate;
    const pathname = new URL(route.request().url()).pathname.slice(new URL(base).pathname.length);
    await route.fulfill({path:fileURLToPath(new URL(pathname, site))});
  });
  await page.goto(`${base}?arch=x86&kernel=v7.3&compare=v1.0&q=chown&lang=en`);
  await intercepted;
  await ready(page);
  await page.evaluate(() => { location.hash = '#sys-v1.0%3A16%3Achown'; });
  await page.waitForFunction(() => document.querySelector('#compare-status').textContent.includes('Loading'));
  const received = page.waitForResponse(response => response.url().includes('/v1.0/'));
  release();
  await received;
  await page.locator('[id="detail-v1.0:16:chown"]').waitFor();
  assert.equal(decodeURIComponent(new URL(page.url()).hash), '#sys-v1.0:16:chown');
});

test('an open call names the tab and links to its permanent page in the reader\'s language', async t => {
  const page = await openPage(t);
  await page.goto(`${base}?arch=x64&kernel=v7.3&lang=en`);
  await page.waitForFunction(() => document.title === 'x86-64 · Linux 7.3 · System Call Reference');
  await page.locator('[data-call="v7.3:257:openat"]').click();
  assert.equal(await page.title(), 'openat (257) · x86-64 · Linux 7.3 · System Call Reference');
  const permanent = page.locator('.detail-row').getByRole('link', { name: 'Permanent page for this call (all ABIs)' });
  assert.equal(await permanent.getAttribute('href'), '/syscall-test/call/openat/');
  await page.locator('[data-call="v7.3:257:openat"]').click();
  assert.equal(await page.title(), 'x86-64 · Linux 7.3 · System Call Reference');

  // A linked detail is named as soon as its table arrives, in the selected language and ABI.
  await page.goto(`${base}?arch=arm64&kernel=v7.3&lang=tr#sys-v7.3%3A56%3Aopenat`);
  await page.locator('.detail-row').waitFor();
  assert.equal(await page.title(), 'openat (56) · AArch64 · Linux 7.3 · Sistem Çağrıları Referansı');
  assert.equal(await page.locator('.detail-row a[href$="/tr/call/openat/"]').count(), 1);
  await page.goto(`${base}?lang=tr`);
  await page.waitForFunction(() => document.querySelector('[data-static-page="call/"]').getAttribute('href') === '/syscall-test/tr/call/');
  const architecture=new URL(await page.locator('#architecture-links a').filter({hasText:'AArch64'}).getAttribute('href'),base);
  assert.equal(architecture.searchParams.get('arch'),'arm64');
  assert.equal(architecture.searchParams.get('lang'),'tr');
});

test('generated pages are readable without JavaScript and fit a phone', async t => {
  const page = await openPage(t, { javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
  await page.goto(base);
  // Crawlable links: present in the served HTML, not rendered by the application.
  assert.equal(await page.locator('#architecture-links a[href="/syscall-test/arch/x64/"]').count(), 1);
  assert.equal(await page.locator('.static-links a[href="/syscall-test/call/"]').count(), 1);
  assert.equal(await page.locator('#architecture-links a, .static-links a').count(), 13);

  await page.goto(`${base}call/openat/`);
  assert.equal(await page.title(), 'openat — Linux system call numbers by architecture (Linux 7.3)');
  assert.equal(await page.locator('link[rel="canonical"]').getAttribute('href'), 'https://zaryob.github.io/syscall/call/openat/');
  assert.equal(await page.locator('link[hreflang="tr"]').getAttribute('href'), 'https://zaryob.github.io/syscall/tr/call/openat/');
  assert.equal(await page.locator('link[hreflang="x-default"]').getAttribute('href'), 'https://zaryob.github.io/syscall/call/openat/');
  const crumbs = JSON.parse(await page.locator('script[type="application/ld+json"]').textContent());
  assert.equal(crumbs['@type'], 'BreadcrumbList');
  assert.deepEqual(crumbs.itemListElement.map(item => item.item), ['https://zaryob.github.io/syscall/', 'https://zaryob.github.io/syscall/call/', 'https://zaryob.github.io/syscall/call/openat/']);
  const row = page.locator('.static-numbers tbody tr', { has: page.getByRole('link', { name: 'AArch64', exact: true }) });
  assert.deepEqual((await row.locator('td').allTextContents()).slice(0, 2), ['56', '0x38']);
  // The wide table scrolls inside its own region; the page itself does not.
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  assert.equal(await page.locator('.static-scroll').first().evaluate(node => node.scrollWidth > node.clientWidth), true);

  await page.goto(`${base}tr/arch/arm64/`);
  assert.equal(await page.locator('html').getAttribute('lang'), 'tr');
  assert.equal(await page.locator('h1').textContent(), 'AArch64 Linux sistem çağrısı tablosu Linux 7.3');
  assert.equal(await page.locator('tbody th#openat a').getAttribute('href'), '../../../tr/call/openat/');
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
});

test('choosing a language on a generated page opens its translation', async t => {
  const page = await openPage(t);
  await page.goto(`${base}call/openat/`);
  await page.locator('#console-language-select').selectOption('tr');
  await page.locator('html[lang="tr"]').waitFor({ state: 'attached' });
  assert.equal(new URL(page.url()).pathname, '/syscall-test/tr/call/openat/');
  assert.equal(await page.locator('h1 code').textContent(), 'openat');
});

test('compact lookup reaches real rows before the fold and restores active advanced filters', async t => {
  const page = await openPage(t, { viewport: { width: 390, height: 844 } });
  await page.goto(`${base}?arch=x64&lang=en`);
  await page.locator('#rows tr').first().waitFor();
  assert.equal(await page.locator('#advanced-options').getAttribute('open'), null);
  assert.equal(await page.locator('#convention-strip').isVisible(), false);
  const row = await page.locator('#rows tr').first().boundingBox();
  assert.ok(row.y < 800, `first row starts at ${row.y}px`);
  await page.locator('#advanced-options > summary').click();
  await page.locator('#hex').check();
  await page.reload();
  await page.locator('#rows tr').first().waitFor();
  assert.notEqual(await page.locator('#advanced-options').getAttribute('open'), null);
  assert.equal(await page.locator('#hex').isChecked(), true);
  assert.match(await page.locator('#rows tr').first().textContent(), /0x0/);
});

test('a vertical swipe over the table scrolls the page on phones and keeps the heading row under the site header', async t => {
  const swipe = (page, gesture) => page.context().newCDPSession(page).then(cdp => cdp.send('Input.synthesizeScrollGesture', { gestureSourceType: 'touch', preventFling: true, speed: 1200, ...gesture }));
  for (const viewport of [{ width: 390, height: 844 }, { width: 844, height: 390 }]) {
    const page = await openPage(t, { viewport, isMobile: true, hasTouch: true });
    await page.goto(`${base}?arch=x64&lang=en`);
    await page.locator('#rows tr').first().waitFor();
    const scroller = page.locator('#table-scroll');
    await scroller.evaluate(element => element.scrollIntoView({ block: 'start', behavior: 'instant' }));
    const start = await page.evaluate(() => scrollY);
    await swipe(page, { x: viewport.width / 2, y: viewport.height - 60, yDistance: -Math.round(viewport.height / 2) });
    const moved = await page.evaluate(() => scrollY) - start;
    assert.ok(moved > viewport.height / 3, `page moved ${moved}px in ${viewport.width}x${viewport.height}`);
    assert.equal(await scroller.evaluate(element => element.scrollTop), 0);
    await page.waitForFunction(() => {
      const heading = document.querySelector('#syscall-table thead th:nth-child(2)').getBoundingClientRect().top;
      return Math.abs(heading - document.querySelector('.console-header').getBoundingClientRect().bottom) < 1;
    });
    await swipe(page, { x: viewport.width - 40, y: viewport.height - 60, xDistance: -200 });
    assert.ok(await scroller.evaluate(element => element.scrollLeft) > 100, 'argument columns still scroll sideways');
  }
  const desktop = await openPage(t, { viewport: { width: 1440, height: 900 } });
  await desktop.goto(`${base}?arch=x64&lang=en`);
  await desktop.locator('#rows tr').first().waitFor();
  assert.equal(await desktop.locator('#table-scroll').evaluate(element => getComputedStyle(element).maxHeight), `${900 - 120}px`);
});

test('the calling-convention, errno, signal and ioctl tables scroll with the page on phones', async t => {
  const swipe = (page, gesture) => page.context().newCDPSession(page).then(cdp => cdp.send('Input.synthesizeScrollGesture', { gestureSourceType: 'touch', preventFling: true, speed: 1200, ...gesture }));
  const tables = [['?lang=en', 'Calling conventions'], ['errno/?arch=x64&lang=en', 'errno values for the selected architecture'], ['signals/?arch=x64&lang=en', 'Signals for the selected architecture'], ['ioctl/?arch=x64&lang=en', 'ioctl commands for the selected architecture'], ['ioctl/?arch=x64&lang=en', 'Registered magic numbers']];
  for (const viewport of [{ width: 390, height: 844 }, { width: 844, height: 390 }]) {
    for (const [address, label] of tables) {
      const page = await openPage(t, { viewport, isMobile: true, hasTouch: true });
      await page.goto(base + address);
      const scroller = page.locator(`.table-scroll[aria-label="${label}"]`);
      await scroller.locator('tbody tr').nth(8).waitFor();
      await scroller.evaluate(element => element.scrollIntoView({ block: 'start', behavior: 'instant' }));
      const start = await page.evaluate(() => scrollY);
      await swipe(page, { x: viewport.width / 2, y: viewport.height - 60, yDistance: -Math.round(viewport.height / 2) });
      const moved = await page.evaluate(() => scrollY) - start;
      assert.ok(moved > viewport.height / 3, `${label}: page moved ${moved}px in ${viewport.width}x${viewport.height}`);
      assert.equal(await scroller.evaluate(element => element.scrollTop), 0, label);
      await page.waitForFunction(element => {
        const heading = element.querySelector('thead th').getBoundingClientRect().top;
        return Math.abs(heading - document.querySelector('.console-header').getBoundingClientRect().bottom) < 1;
      }, await scroller.elementHandle());
      if (viewport.width < 600) {
        await swipe(page, { x: viewport.width - 40, y: viewport.height - 60, xDistance: -200 });
        assert.ok(await scroller.evaluate(element => element.scrollLeft) > 100, `${label}: wide columns still scroll sideways`);
      }
    }
  }
  const desktop = await openPage(t, { viewport: { width: 1440, height: 900 } });
  for (const [address, label] of tables) {
    await desktop.goto(base + address);
    const scroller = desktop.locator(`.table-scroll[aria-label="${label}"]`);
    await scroller.locator('tbody tr').first().waitFor();
    assert.equal(await scroller.evaluate(element => getComputedStyle(element).maxHeight), `${900 - 120}px`, label);
    assert.equal(await scroller.evaluate(element => element.querySelector('table').style.getPropertyValue('--head-offset')), '', label);
  }
});

test('submitting a search leaves the field and brings the count and first result into view', async t => {
  const page = await openPage(t, { viewport: { width: 390, height: 500 }, isMobile: true, hasTouch: true });
  const inView = () => page.evaluate(() => {
    const header = document.querySelector('.console-header').getBoundingClientRect().bottom;
    const results = document.getElementById('results').getBoundingClientRect();
    const row = document.querySelector('#rows .syscall-row').getBoundingClientRect();
    return results.top >= header && row.bottom <= innerHeight;
  });
  await page.goto(`${base}?arch=x64&kernel=v7.3&lang=en`);
  await page.locator('#rows tr').first().waitFor();
  await page.locator('#search').fill('openat');
  assert.match(await page.locator('#results').textContent(), /^2 of \d+ entries$/);
  assert.equal(await inView(), false);
  await page.locator('#search').press('Enter');
  await page.waitForFunction(() => document.activeElement !== document.getElementById('search'));
  assert.equal(await page.evaluate(() => document.activeElement.dataset.call), 'v7.3:257:openat');
  await page.waitForFunction(() => {
    const header = document.querySelector('.console-header').getBoundingClientRect().bottom;
    const results = document.getElementById('results').getBoundingClientRect();
    return results.top >= header && document.querySelector('#rows .syscall-row').getBoundingClientRect().bottom <= innerHeight;
  });
  assert.equal(await page.locator('.detail-row').count(), 0);

  await page.locator('#search').fill('openat2');
  await page.locator('#search').press('Enter');
  await page.locator('.detail-row').waitFor();
  assert.equal(await page.locator('[data-call="v7.3:437:openat2"]').getAttribute('aria-expanded'), 'true');
  assert.equal(decodeURIComponent(new URL(page.url()).hash), '#sys-v7.3:437:openat2');
  await page.waitForFunction(() => document.getElementById('results').getBoundingClientRect().top >= document.querySelector('.console-header').getBoundingClientRect().bottom);
  assert.equal(await inView(), true);
});

test('phones pin only the name column, show the number in the name cell and keep sorting by number', async t => {
  const pinned = page => page.evaluate(() => {
    const box = document.getElementById('table-scroll').getBoundingClientRect();
    const name = document.querySelector('#syscall-table thead th:nth-child(2)').getBoundingClientRect();
    return { share: (name.right - box.left) / box.width, numberColumn: getComputedStyle(document.querySelector('#syscall-table thead th')).display };
  });
  const phone = await openPage(t, { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await phone.goto(`${base}?arch=x64&lang=en`);
  await ready(phone);
  let layout = await pinned(phone);
  assert.equal(layout.numberColumn, 'none');
  assert.ok(layout.share <= 0.37, `name column takes ${Math.round(layout.share * 100)}% of the box at 390px`);
  const openat = phone.locator('#rows tr[id$=":openat"]');
  assert.equal(await openat.locator('.call-identity .inline-number').textContent(), '#257');
  assert.equal(await openat.locator('.call-identity .inline-number').isVisible(), true);
  // The number sort stays a real, labelled button that keyboards and screen readers reach.
  const sortNumber = phone.getByRole('button', { name: /^No\./ });
  assert.equal(await sortNumber.count(), 1);
  await sortNumber.focus();
  await phone.keyboard.press('Enter');
  assert.match(await sortNumber.textContent(), /↓/);
  assert.equal(await phone.locator('#syscall-table thead th').first().getAttribute('aria-sort'), 'descending');
  const numbers = await phone.locator('#rows .inline-number').evaluateAll(cells => cells.slice(0, 3).map(cell => Number(cell.textContent.slice(1))));
  assert.ok(numbers[0] > numbers[1] && numbers[1] > numbers[2], `descending numbers ${numbers}`);
  await phone.getByRole('button', { name: /^System call/ }).click();
  assert.equal(await phone.locator('#syscall-table thead th').nth(1).getAttribute('aria-sort'), 'ascending');
  assert.match(await sortNumber.textContent(), /^No\.$/);
  await phone.locator('#advanced-options > summary').click();
  await phone.locator('#hex').check();
  assert.equal(await openat.locator('.inline-number').textContent(), '#0x101');
  // The row still opens its details and keeps its permalink.
  await openat.locator('.call-name').click();
  await phone.locator('.detail-row').waitFor();
  assert.equal(decodeURIComponent(new URL(phone.url()).hash), '#sys-v7.3:257:openat');

  const small = await openPage(t, { viewport: { width: 320, height: 568 }, isMobile: true, hasTouch: true });
  await small.addInitScript(() => document.addEventListener('DOMContentLoaded', () => document.head.insertAdjacentHTML('beforeend', '<style>html { font-size: 200% !important }</style>')));
  await small.goto(`${base}?arch=x64&lang=en`);
  await ready(small);
  layout = await pinned(small);
  assert.ok(layout.share <= 0.37, `name column takes ${Math.round(layout.share * 100)}% of the box at 320px and 200% text`);
  assert.equal(await small.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);

  const desktop = await openPage(t, { viewport: { width: 1440, height: 900 } });
  await desktop.goto(`${base}?arch=x64&lang=en`);
  await ready(desktop);
  assert.equal((await pinned(desktop)).numberColumn, 'table-cell');
  assert.equal(await desktop.locator('#rows .inline-number').first().isVisible(), false);
  assert.equal(await desktop.locator('#sort-number-narrow').isVisible(), false);
  assert.equal(await desktop.locator('#rows tr[id$=":openat"] .call-number').textContent(), '257');
});

test('architecture pages jump by number range and filter rows, and keep the range links without JavaScript', async t => {
  const big = page => page.addInitScript(() => document.addEventListener('DOMContentLoaded', () => document.head.insertAdjacentHTML('beforeend', '<style>html { font-size: 200% !important }</style>')));
  const landing = page => page.evaluate(() => ({
    target: document.getElementById('n-200').getBoundingClientRect().top,
    bar: document.querySelector('.static-ranges').getBoundingClientRect().bottom,
    header: document.querySelector('.console-header').getBoundingClientRect().bottom,
    both: document.documentElement.classList.contains('static-filter-sticky'),
    sticky: (document.documentElement.classList.contains('static-filter-sticky') ? document.querySelector('.static-filter').offsetHeight : 0) + document.querySelector('.static-ranges').offsetHeight,
  }));
  for (const [viewport, zoom] of [[{ width: 390, height: 844 }, false], [{ width: 320, height: 568 }, true], [{ width: 1440, height: 900 }, false]]) {
    const page = await openPage(t, { viewport, isMobile: viewport.width < 800, hasTouch: viewport.width < 800, reducedMotion: 'reduce' });
    if (zoom) await big(page);
    await page.goto(`${base}tr/arch/x64/`);
    await page.locator('.static-calls tbody tr').nth(150).scrollIntoViewIfNeeded();
    await page.getByRole('navigation', { name: 'Sistem çağrısı numarası aralığına atla' }).getByRole('link', { name: '200–299' }).click();
    await page.waitForFunction(() => location.hash === '#n-200');
    const where = await landing(page);
    // The row lands just below the sticky block, which stays small.
    assert.ok(where.target >= where.bar && where.target - where.bar <= 12, `${viewport.width}px: row at ${where.target}, bar ends at ${where.bar}`);
    assert.ok(where.sticky <= viewport.height * 0.15, `${viewport.width}px: sticky block ${where.sticky}px`);
    const searchLink = page.locator('.static-filter-link');
    assert.equal(await searchLink.isVisible(), !where.both);
    if (!where.both) {
      await searchLink.click();
      assert.equal(await page.evaluate(() => document.activeElement.id), 'static-filter');
    }
  }

  const page = await openPage(t, { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await page.goto(`${base}arch/x64/`);
  const filter = page.getByRole('searchbox', { name: 'Search this table' });
  const rows = page.locator('.static-calls tbody tr:not([hidden])');
  const total = await rows.count();
  await filter.fill('openat');
  assert.deepEqual(await rows.locator('th code').allTextContents(), ['openat', 'openat2']);
  assert.equal(await page.getByRole('status').textContent(), `2 / ${total} rows`);
  await filter.fill('0x101');
  assert.deepEqual(await rows.locator('th code').allTextContents(), ['openat']);
  await filter.press('Enter');
  assert.equal(await page.evaluate(() => document.activeElement.textContent), 'openat');
  // A range link clears the filter so its row exists.
  await page.locator('.static-ranges a[href="#n-200"]').click();
  assert.equal(await rows.count(), total);
  assert.equal(await page.getByRole('status').textContent(), '');
  await page.goto(`${base}tr/arch/x64/`);
  await page.getByRole('searchbox', { name: 'Ara (bu tabloda)' }).fill('257');
  assert.equal(await page.getByRole('status').textContent(), `1 / ${total} satır`);

  const plain = await openPage(t, { javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
  await plain.goto(`${base}tr/arch/x64/`);
  assert.equal(await plain.locator('.static-filter').isVisible(), false);
  assert.equal(await plain.locator('.static-filter-link').isVisible(), false);
  assert.deepEqual(await plain.locator('.static-ranges li a').evaluateAll(links => links.map(link => link.getAttribute('href'))), ['#n-0', '#n-100', '#n-200', '#n-300', '#n-400']);
  await plain.locator('.static-ranges a[href="#n-200"]').click();
  const row = await plain.locator('#n-200').boundingBox();
  const header = await plain.locator('.console-header').boundingBox();
  assert.ok(row.y >= header.y + header.height, `row at ${row.y} under a ${header.height}px header`);
  assert.equal(await plain.locator('#n-200 td').first().textContent(), '200');
});

test('advanced options start closed on desktop and open for any active option', async t => {
  const page = await openPage(t, { viewport: { width: 1440, height: 900 } });
  const panel = page.locator('#advanced-options');
  await page.goto(`${base}?arch=x64&lang=en`);
  await ready(page);
  assert.equal(await panel.getAttribute('open'), null);
  assert.equal(await page.locator('#convention-strip').isVisible(), true);
  assert.match(await page.locator('#convention-strip').textContent(), /ENTRY.*NR.*RETURN.*Argument locations.*RET2.*Clobber/);
  await page.goto(`${base}?arch=x86&kernel=v7.3&compare=v6.6&lang=en`);
  await ready(page);
  assert.notEqual(await panel.getAttribute('open'), null);
  await page.goto(`${base}?arch=x64&lang=en`);
  await ready(page);
  await page.locator('#advanced-options > summary').click();
  await page.locator('#show-unimplemented').check();
  assert.notEqual(await panel.getAttribute('open'), null);
  await page.locator('#show-unimplemented').uncheck();
  assert.notEqual(await panel.getAttribute('open'), null);
  await page.goBack();
  assert.notEqual(await panel.getAttribute('open'), null);
});

test('architecture links are single entries with a usable no-script fallback', async t => {
  const page = await openPage(t);
  await page.goto(`${base}?lang=en`);
  const links=page.locator('#architecture-links a');
  await links.first().waitFor();
  assert.equal(await links.count(),12);
  assert.equal(await page.locator('.static-table-link').count(),0);
  await links.filter({hasText:'x86-64'}).click();
  await ready(page);
  assert.equal(await page.locator('#syscall-table thead th').count(),8);
  assert.equal(await page.locator('.row-description').count(),0);
  await page.locator('.call-name').first().click();
  assert.ok(await page.locator('.detail-description').textContent());
});

test('source paragraphs keep sentence boundaries in both languages', async t => {
  const page=await openPage(t);
  await page.goto(`${base}?lang=tr#sources`);
  const intro=page.locator('.source-intro');
  assert.match(await intro.textContent(), /kodundan üretilir\. Mimariye özgü/);
  assert.match(await intro.textContent(), /Makefile.syscalls dosyasını izler\. Yazmaç/);
  await page.locator('[data-console-language]').selectOption('en');
  assert.match(await intro.textContent(), /kernel source\. Architecture-specific/);
  assert.match(await intro.textContent(), /Makefile.syscalls\. Register/);
});
