/**
 * Factle shared leaderboard: Cloudflare Worker + D1. Same shape as Yogle's worker.
 *
 * Unlike Yogle and ridd-le, no score is client-reported: the browser sends (day, round, pick, ms) and this worker
 * judges the pick against its own bundled copy of the answers and computes the points with the same function
 * the site uses. What it can't verify is the time taken (a modified browser could claim it answered fast) and
 * whether the player looked up the public answer files; that is the accepted trade-off of a free static game.
 *   - player ids/tokens are issued here (/api/session)
 *   - the day must be a scheduled day, not in the future; late (archive replay) = submitted after that UTC day
 *   - rounds must be played in order, once each (insert-only, the first pick counts)
 *   - ms >= MIN_MS
 */
import { MIN_MS, ROUNDS, roundScore, todayKey, validDay } from '../../site/js/daily.js';
import index from '../../site/data/index.json';

const MAX_NAME = 20;
const BOARD_SIZE = 20;

function validateName(raw) {
  if (typeof raw !== 'string') return null;
  const name = raw.replace(/[\u0000-\u001f\u007f]/g, '').replace(/\s+/g, ' ').trim();
  if (!name || [...name].length > MAX_NAME) return null;
  return name;
}

async function sha256Hex(text) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

// --- HTTP plumbing ---

function allowedOrigin(request, env) {
  const origin = request.headers.get('Origin') || '';
  const allowed = (env.ALLOWED_ORIGINS || '').split(',').map((s) => s.trim()).filter(Boolean);
  if (!allowed.length) return '*';
  return allowed.includes(origin) ? origin : allowed[0];
}

function cors(request, env) {
  return {
    'Access-Control-Allow-Origin': allowedOrigin(request, env),
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
    Vary: 'Origin',
  };
}

function json(request, env, body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...cors(request, env) } });
}

function fail(request, env, code, message, status) {
  return json(request, env, { error: code, message }, status);
}

const hits = new Map(); // in-memory, per isolate: enough to blunt a burst
function rateLimited(ip, bucket, limit) {
  const now = Date.now(), key = `${bucket}:${ip}`;
  const recent = (hits.get(key) ?? []).filter((t) => now - t < 3600_000);
  const over = recent.length >= limit;
  if (!over) recent.push(now);
  hits.set(key, recent);
  return over;
}

// --- routes ---

async function handleSession(request, env, ip) {
  if (rateLimited(ip, 'session', 30)) return fail(request, env, 'rate_limited', 'Too many new sessions from here.', 429);
  const playerId = crypto.randomUUID(), token = crypto.randomUUID();
  await env.DB.prepare('INSERT INTO players (id, token_hash, created_at) VALUES (?, ?, ?)')
    .bind(playerId, await sha256Hex(token), new Date().toISOString()).run();
  return json(request, env, { playerId, token });
}

async function verifyPlayer(env, playerId, token) {
  if (typeof playerId !== 'string' || typeof token !== 'string' || !playerId || !token) return false;
  const row = await env.DB.prepare('SELECT token_hash FROM players WHERE id = ?').bind(playerId).first();
  return !!row && row.token_hash === (await sha256Hex(token));
}

const view = (r, rank, playerId) => ({
  rank, name: r.display_name, total: r.total, played: r.played,
  rounds: r.rounds ? r.rounds.split(',').map(Number) : [], you: r.player_id === playerId,
});

export async function fetchBoard(env, day, late, playerId) {
  const lateN = late ? 1 : 0;
  const { results } = await env.DB.prepare(
    `SELECT player_id, display_name, total, played, rounds, last_at FROM totals
      WHERE day_key = ? AND is_late = ? ORDER BY total DESC, last_at ASC LIMIT ?`,
  ).bind(day, lateN, BOARD_SIZE).all();
  const top = (results ?? []).map((r, i) => view(r, i + 1, playerId));
  const stats = await env.DB.prepare('SELECT players, top FROM day_stats WHERE day_key = ? AND is_late = ?')
    .bind(day, lateN).first();
  let you = null;
  if (playerId && !top.some((r) => r.you)) {
    const mine = await env.DB.prepare(
      'SELECT player_id, display_name, total, played, rounds, last_at FROM totals WHERE player_id = ? AND day_key = ? AND is_late = ?',
    ).bind(playerId, day, lateN).first();
    if (mine) {
      const above = await env.DB.prepare(
        `SELECT COUNT(*) AS n FROM totals WHERE day_key = ? AND is_late = ?
           AND (total > ? OR (total = ? AND last_at < ?))`,
      ).bind(day, lateN, mine.total, mine.total, mine.last_at).first();
      you = view(mine, (above?.n ?? 0) + 1, playerId);
    }
  }
  return { day, late: !!late, players: stats?.players ?? 0, top, you };
}

async function handleLeaderboard(request, env) {
  const url = new URL(request.url);
  const day = url.searchParams.get('day') || todayKey();
  if (!validDay(day)) return fail(request, env, 'bad_day', 'Invalid day.', 400);
  return json(request, env, await fetchBoard(env, day, url.searchParams.get('late') === '1', url.searchParams.get('playerId')));
}

async function handleDays(request, env) {
  const url = new URL(request.url);
  const to = url.searchParams.get('to') || todayKey();
  const from = url.searchParams.get('from') || index.first;
  if (!validDay(from) || !validDay(to)) return fail(request, env, 'bad_day', 'Invalid day.', 400);
  const { results } = await env.DB.prepare(
    'SELECT day_key, is_late, players, top FROM day_stats WHERE day_key BETWEEN ? AND ?',
  ).bind(from, to).all();
  const days = {};
  for (const r of results ?? []) {
    days[r.day_key] ??= { players: 0, top: null, latePlayers: 0 };
    if (r.is_late) days[r.day_key].latePlayers = r.players;
    else Object.assign(days[r.day_key], { players: r.players, top: r.top });
  }
  return json(request, env, { days });
}

async function handleRound(request, env, ip) {
  if (rateLimited(ip, 'round', 300)) return fail(request, env, 'rate_limited', 'Too many submissions from here. Try again later.', 429);
  let body;
  try { body = await request.json(); } catch { return fail(request, env, 'bad_request', 'Invalid JSON.', 400); }
  const { playerId, token, day, round, pick, ms } = body ?? {};
  if (!(await verifyPlayer(env, playerId, token))) return fail(request, env, 'bad_session', 'Invalid or missing session. Reload the page.', 401);
  const today = todayKey();
  if (!validDay(day) || !index.answers[day]) return fail(request, env, 'bad_day', 'There is no game for that day.', 400);
  if (day > today) return fail(request, env, 'bad_day', "That day hasn't happened yet.", 400);
  if (!Number.isInteger(round) || round < 0 || round >= ROUNDS) return fail(request, env, 'bad_round', 'Invalid round.', 400);
  if (!Number.isInteger(pick) || pick < 0 || pick >= 5) return fail(request, env, 'bad_pick', 'Invalid pick.', 400);
  if (!Number.isInteger(ms) || ms < MIN_MS || ms > 86400_000) return fail(request, env, 'bad_time', 'That was impossibly fast.', 400);
  const name = validateName(body.name);
  if (!name) return fail(request, env, 'bad_name', `Name must be 1-${MAX_NAME} characters.`, 400);

  const late = day !== today ? 1 : 0;
  const prev = await env.DB.prepare('SELECT COUNT(*) AS n FROM picks WHERE player_id = ? AND day_key = ? AND is_late = ?')
    .bind(playerId, day, late).first();
  const done = prev?.n ?? 0;
  if (round < done) return fail(request, env, 'already', 'You already answered that round.', 409);
  if (round > done) return fail(request, env, 'out_of_order', 'Rounds must be played in order.', 409);

  const correct = pick === index.answers[day][round];
  const points = roundScore(correct, ms);
  const now = new Date().toISOString();
  const stmts = [
    env.DB.prepare(
      `INSERT INTO picks (id, player_id, day_key, is_late, round, pick, ms, correct, points, submitted_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).bind(crypto.randomUUID(), playerId, day, late, round, pick, ms, correct ? 1 : 0, points, now),
    env.DB.prepare(
      `INSERT INTO totals (player_id, day_key, is_late, display_name, total, played, rounds, last_at)
       VALUES (?, ?, ?, ?, ?, 1, ?, ?)
       ON CONFLICT (player_id, day_key, is_late) DO UPDATE SET
         total = total + excluded.total, played = played + 1, rounds = rounds || ',' || excluded.rounds,
         last_at = excluded.last_at`,
    ).bind(playerId, day, late, name, points, String(points), now),
  ];
  if (round === 0) {
    stmts.push(env.DB.prepare(
      `INSERT INTO day_stats (day_key, is_late, players, top) VALUES (?, ?, 1, 0)
       ON CONFLICT (day_key, is_late) DO UPDATE SET players = players + 1`,
    ).bind(day, late));
  }
  stmts.push(env.DB.prepare(
    `UPDATE day_stats SET top = MAX(top, (SELECT total FROM totals WHERE player_id = ? AND day_key = ? AND is_late = ?))
      WHERE day_key = ? AND is_late = ?`,
  ).bind(playerId, day, late, day, late));
  try {
    await env.DB.batch(stmts);
  } catch (e) {
    if (String(e).includes('UNIQUE')) return fail(request, env, 'already', 'You already answered that round.', 409);
    throw e;
  }
  return json(request, env, { ok: true, late: !!late, correct, points, fake: index.answers[day][round] });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === 'OPTIONS') return new Response(null, { headers: cors(request, env) });
    const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
    try {
      if (url.pathname === '/api/session' && request.method === 'POST') return await handleSession(request, env, ip);
      if (url.pathname === '/api/round' && request.method === 'POST') return await handleRound(request, env, ip);
      if (url.pathname === '/api/leaderboard' && request.method === 'GET') return await handleLeaderboard(request, env);
      if (url.pathname === '/api/days' && request.method === 'GET') return await handleDays(request, env);
      return fail(request, env, 'not_found', 'No such endpoint.', 404);
    } catch (err) {
      console.error(err);
      return fail(request, env, 'server_error', 'Something broke. Try again.', 500);
    }
  },
};
