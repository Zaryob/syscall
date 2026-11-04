// SPDX-License-Identifier: GPL-2.0-only
import assert from 'node:assert/strict';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const site = new URL('../_site-test/', import.meta.url);
const base = 'http://localhost/syscall-test/';

async function openPage(t) {
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const context = await browser.newContext({ permissions: ['clipboard-read', 'clipboard-write'] });
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
