// Shared by the site and the leaderboard worker (worker/src/index.js imports this file),
// so the day, the puzzle number and the score can never disagree between the two.

export const EPOCH = '2026-10-10'; // puzzle #1. Never change once live: it renumbers every day.
export const ROUNDS = 5;
export const MAX_POINTS = 100;
export const GRACE_SECONDS = 15;   // full points if you answer within this
export const MIN_POINTS = 20;      // a correct answer is always worth at least this
export const MIN_MS = 1500;        // faster than this isn't a human reading five facts

/** UTC day key YYYY-MM-DD. */
export function todayKey(now = new Date()) {
  return now.toISOString().slice(0, 10);
}

export function dayNumber(day) {
  return Math.round((Date.parse(`${day}T00:00:00Z`) - Date.parse(`${EPOCH}T00:00:00Z`)) / 864e5) + 1;
}

export function addDays(day, n) {
  return new Date(Date.parse(`${day}T00:00:00Z`) + n * 864e5).toISOString().slice(0, 10);
}

export function msUntilNextUtcDay(now = Date.now()) {
  return Math.ceil((now + 1) / 864e5) * 864e5 - now;
}

export function validDay(day) {
  return typeof day === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(day)
    && !Number.isNaN(Date.parse(`${day}T00:00:00Z`))
    && new Date(`${day}T00:00:00Z`).toISOString().slice(0, 10) === day;
}

/**
 * Points for one round: 0 if wrong. If right, 100 within the first 15 s, then one point less per second,
 * never below 20.
 */
export function roundScore(correct, ms) {
  if (!correct) return 0;
  const s = Math.max(0, ms) / 1000;
  return Math.max(MIN_POINTS, Math.round(MAX_POINTS - Math.max(0, s - GRACE_SECONDS)));
}

/** One emoji per round: wrong, right but slow (< 80), right and quick. */
export function roundEmoji(points) {
  if (points === null || points === undefined) return '⬜';
  if (points === 0) return '🟥';
  return points >= 80 ? '🟩' : '🟨';
}
