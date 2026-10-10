import test from 'node:test';
import assert from 'node:assert/strict';
import { EPOCH, addDays, dayNumber, msUntilNextUtcDay, roundEmoji, roundScore, todayKey, validDay } from '../site/js/daily.js';

test('the day is the UTC date, whatever the local timezone', () => {
  // 23:30 in New York on 9 Oct is already 10 Oct in UTC; 00:30 BST on 10 Oct is still 9 Oct in UTC
  assert.equal(todayKey(new Date('2026-10-09T23:30:00-04:00')), '2026-10-10');
  assert.equal(todayKey(new Date('2026-10-10T00:30:00+01:00')), '2026-10-09');
  assert.equal(todayKey(new Date('2026-10-09T23:59:59.999Z')), '2026-10-09');
  assert.equal(todayKey(new Date('2026-10-10T00:00:00.000Z')), '2026-10-10');
});

test('puzzle numbers count from the epoch, across DST and leap days', () => {
  assert.equal(dayNumber(EPOCH), 1);
  assert.equal(dayNumber('2026-10-11'), 2);
  assert.equal(dayNumber('2026-10-25'), 16); // UK clocks change that night
  assert.equal(dayNumber('2028-03-01'), dayNumber('2028-02-28') + 2); // 2028 is a leap year
  assert.equal(addDays('2026-12-31', 1), '2027-01-01');
});

test('countdown to the next UTC midnight', () => {
  assert.equal(msUntilNextUtcDay(Date.parse('2026-10-09T23:59:59Z')), 1000);
  assert.equal(msUntilNextUtcDay(Date.parse('2026-10-10T00:00:00Z')), 864e5);
});

test('validDay rejects impossible dates', () => {
  assert.ok(validDay('2026-02-28'));
  assert.ok(!validDay('2026-02-30'));
  assert.ok(!validDay('2026-1-01'));
  assert.ok(!validDay(null));
});

test('round score: 0 if wrong, 100 within 15 s, -1/s after, floor 20', () => {
  assert.equal(roundScore(false, 3000), 0);
  assert.equal(roundScore(true, 2000), 100);
  assert.equal(roundScore(true, 15000), 100);
  assert.equal(roundScore(true, 45000), 70);
  assert.equal(roundScore(true, 600000), 20);
  assert.equal(roundEmoji(0), '🟥');
  assert.equal(roundEmoji(85), '🟩');
  assert.equal(roundEmoji(50), '🟨');
});
