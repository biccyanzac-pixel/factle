// Read-only check of the live site: loads, shows today's game and the (real) leaderboard, no errors.
// Does not play, so it never writes to the production leaderboard.
import { chromium } from 'playwright-core';
const URL_ = process.argv[2] || 'https://biccyanzac-pixel.github.io/factle/';
const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true });
const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
const errors = []; page.on('pageerror', (e) => errors.push(e.message)); page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
await page.goto(URL_, { waitUntil: 'networkidle' });
await page.waitForSelector('#daynum:has-text("Factle #")');
await page.waitForSelector('#board:not([hidden])', { timeout: 15000 });
const out = { daynum: await page.textContent('#daynum'), start: await page.textContent('#start-label'),
  board: (await page.textContent('#board')).replace(/\s+/g, ' ').trim().slice(0, 120), errors };
await page.screenshot({ path: 'tools/results/live.png', fullPage: true });
console.log(JSON.stringify(out, null, 1));
await browser.close();
process.exit(errors.length ? 1 : 0);
