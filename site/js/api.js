// Leaderboard client (worker/). Every call fails soft: with no backend the game still works, just without a board.
// The URL comes from data/config.json; ?api=<url> overrides it for local testing.

const SESSION_KEY = 'factle:session';
const NAME_KEY = 'factle:name';
let base;
let memSession = null;

export async function loadConfig() {
  if (base !== undefined) return base;
  try {
    const cfg = await (await fetch('data/config.json', { cache: 'no-cache' })).json();
    const override = new URLSearchParams(location.search).get('api');
    base = (override || cfg.leaderboardUrl || '').replace(/\/+$/, '') || null;
  } catch { base = null; }
  return base;
}

export const enabled = () => !!base;

async function call(path, body) {
  if (!base) throw new Error('No leaderboard configured.');
  const res = await fetch(base + path, body === undefined ? undefined
    : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  let data = null;
  try { data = await res.json(); } catch { /* handled below */ }
  if (!res.ok) {
    const e = new Error(data?.message || `Leaderboard error (HTTP ${res.status}).`);
    e.status = res.status; e.code = data?.error;
    throw e;
  }
  return data;
}

function readSession() { try { return JSON.parse(localStorage.getItem(SESSION_KEY)); } catch { return null; } }
function writeSession(s) { try { localStorage.setItem(SESSION_KEY, JSON.stringify(s)); } catch { /* private mode */ } }

export async function session(fresh = false) {
  if (!fresh) { const s = memSession || readSession(); if (s?.playerId && s?.token) return (memSession = s); }
  memSession = await call('/api/session', {});
  writeSession(memSession);
  return memSession;
}

export function playerId() { return (memSession || readSession())?.playerId ?? null; }
export function savedName() { try { return localStorage.getItem(NAME_KEY) || ''; } catch { return ''; } }
export function saveName(n) { try { localStorage.setItem(NAME_KEY, n); } catch { /* ignore */ } }

/** Record one round's pick. The server judges it and works out the points from the time. */
export async function submitRound({ day, round, pick, ms, name }) {
  const body = { day, round, pick, ms: Math.round(ms), name };
  let s = await session();
  try { return await call('/api/round', { ...s, ...body }); }
  catch (e) {
    if (e.code !== 'bad_session') throw e;
    s = await session(true);
    return call('/api/round', { ...s, ...body });
  }
}

export function board(day, late = false) {
  const pid = playerId();
  return call(`/api/leaderboard?day=${day}${late ? '&late=1' : ''}${pid ? '&playerId=' + encodeURIComponent(pid) : ''}`);
}

export function days(from, to) { return call(`/api/days?from=${from}&to=${to}`); }
