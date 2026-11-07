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
  await page.route(`${base}**`, route => {
    const pathname = new URL(route.request().url()).pathname.slice(new URL(base).pathname.length);
    return route.fulfill({ path: fileURLToPath(new URL(pathname || 'index.html', site)) });
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
  assert.match(await page.locator('#conventions [data-syscall-copy]').textContent(), /PPC_FEATURE2_SCV/);
  assert.match(await page.locator('footer').textContent(), /visit analytics/);
  await page.locator('[data-console-menu]').click();
  await page.locator('[data-console-language]').selectOption('tr');
  await page.locator('[data-console-menu]').click();
  assert.match(await page.locator('#conventions [data-syscall-copy]').textContent(), /alt 32/);
  assert.match(await page.locator('footer').textContent(), /ziyaret analitiği/);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await page.goto(`${base}?arch=x64&lang=tr`);
  await ready(page);
  assert.equal(await page.locator('#kernel option').filter({hasText:'LTS'}).count(), 3);
  assert.match(await page.locator('#release-help').textContent(), /7 Kasım 2026/);
});

test('view and number-format steps restore controls and rendered cells through history', async t => {
  const page = await openPage(t);
  await page.goto(`${base}?arch=x64&kernel=v7.3&q=read&lang=en`);
  await ready(page);
  await page.locator('[data-view="args"]').click();
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
  await page.goBack(); await ready(page);
  assert.equal((await selection(page)).view, 'summary');
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
