// SPDX-License-Identifier: GPL-2.0-only
import assert from 'node:assert/strict';
import test from 'node:test';
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
