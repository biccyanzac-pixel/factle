/**
 * End-to-end test against a running worker (wrangler dev --local = real Miniflare + local D1, no mocks).
 *   npm run db:init:local && npm run dev:local      (in another terminal)
 *   npm test                                         (or: node test/e2e.mjs http://127.0.0.1:8811)
 * Needs today and yesterday to be in site/data/index.json.
 */
import fs from 'node:fs';
import { addDays, roundScore } from '../../site/js/daily.js';

const BASE = process.argv[2] || 'http://127.0.0.1:8811';
const index = JSON.parse(fs.readFileSync(new URL('../../site/data/index.json', import.meta.url)));
const today = new Date().toISOString().slice(0, 10);
const yesterday = addDays(today, -1);
const ans = (d, r) => index.answers[d][r];

let failures = 0;
const check = (label, ok, detail = '') => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? '  ' + detail : ''}`); if (!ok) failures++; };
async function call(path, body) {
  const res = await fetch(BASE + path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined);
  return { status: res.status, body: await res.json() };
}

const a = (await call('/api/session', {})).body, b = (await call('/api/session', {})).body;
check('session issues id + token', !!a.playerId && !!a.token && a.playerId !== b.playerId);

let r = await call('/api/round', { ...a, day: today, round: 0, pick: ans(today, 0), ms: 10000, name: 'Ada' });
check('correct fast pick = 100', r.status === 200 && r.body.correct === true && r.body.points === 100, JSON.stringify(r.body));
r = await call('/api/round', { ...a, day: today, round: 0, pick: (ans(today, 0) + 1) % 5, ms: 9000, name: 'Ada' });
check('a round can only be answered once', r.status === 409 && r.body.error === 'already');
r = await call('/api/round', { ...a, day: today, round: 2, pick: 0, ms: 9000, name: 'Ada' });
check('rounds must be in order', r.status === 409 && r.body.error === 'out_of_order');
r = await call('/api/round', { ...a, day: today, round: 1, pick: (ans(today, 1) + 1) % 5, ms: 9000, name: 'Ada' });
check('wrong pick = 0 (judged by the server)', r.status === 200 && r.body.correct === false && r.body.points === 0);
r = await call('/api/round', { ...a, day: today, round: 2, pick: ans(today, 2), ms: 45000, name: 'Ada' });
check('slow correct pick scored by the server formula', r.body.points === roundScore(true, 45000) && r.body.points === 70);
r = await call('/api/round', { ...a, day: today, round: 3, pick: ans(today, 3), ms: 500, name: 'Ada' });
check('impossibly fast rejected', r.status === 400 && r.body.error === 'bad_time');
r = await call('/api/round', { ...a, day: addDays(today, 1), round: 0, pick: 0, ms: 9000, name: 'Ada' });
check('future day rejected', r.status === 400 && r.body.error === 'bad_day');
r = await call('/api/round', { ...a, day: '2001-01-01', round: 0, pick: 0, ms: 9000, name: 'Ada' });
check('unscheduled day rejected', r.status === 400);
r = await call('/api/round', { ...a, token: 'nope', day: today, round: 3, pick: 0, ms: 9000, name: 'Ada' });
check('bad token rejected', r.status === 401);
r = await call('/api/round', { ...b, day: today, round: 0, pick: ans(today, 0), ms: 20000, name: '' });
check('empty name rejected', r.status === 400 && r.body.error === 'bad_name');

for (let i = 0; i < 5; i++) await call('/api/round', { ...b, day: today, round: i, pick: ans(today, i), ms: 12000, name: 'Bo' });
r = await call(`/api/leaderboard?day=${today}&playerId=${a.playerId}`);
check('board ranks by total', r.body.top.map((x) => `${x.name}:${x.total}`).join(',') === 'Bo:500,Ada:170', JSON.stringify(r.body.top));
check('board has rounds + played + you', r.body.top[1].you === true && r.body.top[1].played === 3 && r.body.top[1].rounds.join(',') === '100,0,70');
check('player count', r.body.players === 2);

if (index.answers[yesterday]) {
  r = await call('/api/round', { ...a, day: yesterday, round: 0, pick: ans(yesterday, 0), ms: 9000, name: 'Ada' });
  check('yesterday goes on the late board', r.status === 200 && r.body.late === true);
  r = await call(`/api/leaderboard?day=${yesterday}&late=1`);
  check('late board separate', r.body.top.length === 1 && r.body.late === true);
} else console.log('SKIP  late board (yesterday not scheduled)');

r = await call(`/api/days?from=${addDays(today, -3)}&to=${today}`);
check('days summary', r.body.days[today]?.players === 2 && r.body.days[today]?.top === 500, JSON.stringify(r.body.days));

console.log(failures ? `\n${failures} FAILED` : '\nall passed');
process.exit(failures ? 1 : 0);
