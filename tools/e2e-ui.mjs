// Browser end-to-end: plays today's 5 rounds in headless Chrome against a local worker, phone + desktop sizes.
//   cd worker && npm run db:init:local && npm run dev:local     (in another terminal)
//   node tools/e2e-ui.mjs
import fs from 'node:fs';
import { chromium } from 'playwright-core';
import { serve } from './serve.mjs';

const API = process.env.API || 'http://127.0.0.1:8811';
const HUB = process.env.HUB || 'http://127.0.0.1:8831'; // jacob.gg hub worker (ratings), run from the jacob.gg repo
const today = new Date().toISOString().slice(0, 10);
const day = JSON.parse(fs.readFileSync(new URL(`../site/data/days/${today}.json`, import.meta.url)));
const srv = await serve(8081);
const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true });
let failures = 0;
const check = (label, ok, detail = '') => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? '  ' + detail : ''}`); if (!ok) failures++; };

const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
const errors = []; page.on('pageerror', (e) => errors.push(e.message)); page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
await page.goto(`http://localhost:8081/?api=${encodeURIComponent(API)}&hub=${encodeURIComponent(HUB)}`);
await page.waitForSelector('#daynum:has-text("Factle #")');
check('day number shown', (await page.textContent('#daynum')).includes(`#${day.number}`));
await page.screenshot({ path: 'tools/results/1-intro-phone.png', fullPage: true });
await page.fill('#name', 'Tester');
await page.click('#start');
for (let r = 0; r < 5; r++) {
  await page.waitForSelector('#facts .fact');
  const texts = await page.$$eval('#facts .fact', (bs) => bs.map((b) => b.textContent));
  check(`round ${r + 1} shows the day's 5 facts`, texts.length === 5 && texts.every((t, i) => t === day.rounds[r].facts[i].text));
  await page.waitForTimeout(1800); // the worker rejects picks faster than 1.5 s
  const pick = r === 1 ? (day.rounds[r].fake + 1) % 5 : day.rounds[r].fake; // get round 2 wrong on purpose
  await page.click(`#facts li:nth-child(${pick + 1}) .fact`);
  if (r === 0) await page.screenshot({ path: 'tools/results/2-round-phone.png', fullPage: true });
  await page.click('#confirm');
  await page.waitForSelector('#reveal:not([hidden])');
  const pts = Number(await page.textContent('#round-score'));
  check(`round ${r + 1} scored ${r === 1 ? '0 when wrong' : '100 when right and quick'}`, r === 1 ? pts === 0 : pts === 100, String(pts));
  const orig = await page.textContent('#original');
  check(`round ${r + 1} reveal shows the real fact`, orig.includes(day.rounds[r].change.old) && (await page.$$('.fact-sources a')).length >= 5);
  if (r === 0) await page.screenshot({ path: 'tools/results/3-reveal-phone.png', fullPage: true });
  await page.waitForTimeout(400); // let the round reach the worker
  await page.click('#next');
}
await page.waitForSelector('#done:not([hidden])');
check('daily total 400/500', (await page.textContent('#daily-score')) === '400');
await page.waitForSelector('#rows .row');
const board = await page.$$eval('#rows .row', (rs) => rs.map((r) => r.textContent));
check('leaderboard lists the player with 400', board.some((t) => t.includes('Tester') && t.includes('400')), JSON.stringify(board));
await page.screenshot({ path: 'tools/results/4-done-phone.png', fullPage: true });
check('weekday level shown (jacob.gg kit)', /·|Sunday special/.test(await page.textContent('#level')));
await page.waitForSelector('#rate .jgg-rate');
await page.focus('#rate .jgg-stars');
await page.keyboard.press('End');
await page.click('#rate .jgg-rate-send');
await page.waitForFunction(() => document.querySelector('#rate .jgg-rate-note').textContent.startsWith('Thanks'));
check('rating sent to the hub', true);

await page.reload();
await page.waitForSelector('#done:not([hidden])');
check('finished state survives a reload', (await page.textContent('#daily-score')) === '400');
await page.click('#archive-browse');
await page.waitForSelector('#archive-list:not([hidden])');
check('archive opens', (await page.textContent('#archive-list')).length > 0);
const scrollW = await page.evaluate(() => document.documentElement.scrollWidth);
check('no horizontal scroll at phone width', scrollW <= 390, String(scrollW));

const desk = await browser.newPage({ viewport: { width: 1280, height: 900 } });
desk.on('pageerror', (e) => errors.push(e.message));
await desk.goto(`http://localhost:8081/?api=${encodeURIComponent(API)}&hub=${encodeURIComponent(HUB)}`);
await desk.waitForSelector('#daynum:has-text("Factle #")');
await desk.screenshot({ path: 'tools/results/5-intro-desktop.png' });

// storage blocked: the page must still work
const ctx = await browser.newContext();
await ctx.addInitScript(() => { Object.defineProperty(window, 'localStorage', { get() { throw new Error('blocked'); } }); });
const blocked = await ctx.newPage();
const blockedErrors = []; blocked.on('pageerror', (e) => blockedErrors.push(e.message));
await blocked.goto(`http://localhost:8081/`);
await blocked.waitForSelector('#daynum:has-text("Factle #")');
await blocked.fill('#name', 'NoStorage');
await blocked.click('#start');
await blocked.waitForSelector('#facts .fact');
check('works with localStorage blocked', blockedErrors.length === 0, blockedErrors.join(' | '));

check('no page errors', errors.length === 0, errors.join(' | '));
await browser.close(); srv.close();
console.log(failures ? `\n${failures} FAILED` : '\nall passed');
process.exit(failures ? 1 : 0);
