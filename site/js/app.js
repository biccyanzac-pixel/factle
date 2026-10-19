// Factle UI: intro -> 5 rounds (pick the fake, timed) -> daily score, share, leaderboard. Archive replays.
import { ROUNDS, addDays, dayNumber, msUntilNextUtcDay, roundEmoji, roundScore, todayKey } from './daily.js';
import * as api from './api.js';
import * as store from './storage.js';

const $ = (id) => document.getElementById(id);
const REPO = 'https://github.com/biccyanzac-pixel/factle';
const SITE = 'https://biccyanzac-pixel.github.io/factle/';

let index = null;          // data/index.json: { first, last, ... }
const dayCache = new Map(); // day -> data/days/<day>.json
let mode = { day: todayKey(), late: false };
let current = null;        // { roundIndex, data, start, pick, timer }

function el(tag, props = {}, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') n.className = v;
    else if (k === 'text') n.textContent = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v);
  }
  for (const c of children) if (c !== null && c !== undefined) n.append(c);
  return n;
}

// A plain show/hide cancels any transition still running on that element, so it can't undo this later.
const show = (id, on = true) => { const e = $(id); e.getAnimations?.().forEach((a) => a.cancel()); e.hidden = !on; };
// The kit's motion (docs/motion-system.md) when it loaded; the same end state without it.
const motion = () => window.JGG?.motion;
const phase = (from, to) => { const m = motion(); if (m && !from.hidden) m.swap(from, to); else { from.hidden = true; to.hidden = false; } };
const scrollTo = (e, block = 'start') => { const m = motion(); m ? m.scroll(e, { block }) : e.scrollIntoView({ block }); };
const countUp = (e, to) => { e.textContent = to; motion()?.settle(e, to); };

async function loadDay(day) {
  if (!dayCache.has(day)) {
    const res = await fetch(`data/days/${day}.json`, { cache: 'no-cache' });
    if (!res.ok) throw new Error(`No game for ${day}.`);
    dayCache.set(day, await res.json());
  }
  return dayCache.get(day);
}

function pad(n) { return String(n).padStart(2, '0'); }

function tickCountdown() {
  const s = Math.floor(msUntilNextUtcDay() / 1000);
  $('countdown').textContent = `Next in ${pad(Math.floor(s / 3600))}:${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}`;
  // a new UTC day started: switch to it unless someone is mid-round
  if (!mode.late && mode.day !== todayKey() && !current) {
    mode = { day: todayKey(), late: false };
    render();
  }
}

// --- views ----------------------------------------------------------------------------------------

function doneCount(day, late) { return store.progress(day, late).rounds.filter(Boolean).length; }

async function render() {
  const { day, late } = mode;
  $('daynum').textContent = `Factle #${dayNumber(day)}${late ? ` · ${day} (played later)` : ''}`;
  if (window.JGG) $('level').replaceChildren(JGG.levelChip(day));
  show('round', false);
  const n = doneCount(day, late);
  if (n >= ROUNDS) {
    show('intro', false);
    renderDone();
  } else {
    show('done', false);
    show('intro', true);
    const scheduled = !index || (day >= index.first && day <= index.last);
    $('start').disabled = !scheduled;
    hideError('start-error');
    if (!scheduled) showError('start-error', "Today's rounds aren't ready yet. Check back soon!");
    $('start-label').textContent = n === 0 ? `Start round 1 of ${ROUNDS}` : `Continue: round ${n + 1} of ${ROUNDS}`;
    const name = api.savedName();
    $('name').value = name;
    show('name-field', !name);
    if (window.JGG) JGG.playingAs({ mount: $('playing-as'), name, onChange: (n) => { api.saveName(n); $('name').value = n; } });
    else { $('playing-as').textContent = name ? `Playing as ${name}.` : ''; show('playing-as', !!name); }
  }
  renderBoard();
}

async function startRound(i) {
  const { day, late } = mode;
  let data;
  try { data = await loadDay(day); }
  catch (e) { showError('start-error', e.message); return; }
  const round = data.rounds[i];
  const from = ['intro', 'done'].map($).find((e) => !e.hidden);
  show('reveal', false);
  from ? phase(from, $('round')) : show('round', true);
  hideError('round-error');
  $('round-label').textContent = `Round ${i + 1} of ${ROUNDS}`;
  $('round-question').textContent = 'Which one is fake?';
  const list = $('facts');
  list.replaceChildren();
  round.facts.forEach((f, j) => {
    const b = el('button', { class: 'fact', type: 'button', 'aria-pressed': 'false', onclick: () => select(j) },
      el('span', { class: 'fact-text', text: f.text }));
    list.append(el('li', {}, b));
  });
  const confirm = $('confirm');
  confirm.hidden = false;
  confirm.disabled = true;
  $('confirm-label').textContent = 'Tap the fact you think is fake';
  const start = store.roundStart(day, late, i);
  current = { roundIndex: i, data, start, pick: null, timer: setInterval(tickTimer, 250) };
  tickTimer();
  list.querySelector('button')?.focus({ preventScroll: true });
  scrollTo($('card'));
}

function tickTimer() {
  if (!current) return;
  const pts = roundScore(true, Date.now() - current.start);
  $('timer-points').textContent = pts;
  $('timer').classList.toggle('low', pts < 60);
}

function select(j) {
  if (!current || current.done) return;
  current.pick = j;
  [...$('facts').querySelectorAll('.fact')].forEach((b, k) => b.setAttribute('aria-pressed', String(k === j)));
  $('confirm').disabled = false;
  $('confirm-label').textContent = "That's the fake";
}

async function confirmPick() {
  if (!current || current.pick === null || current.done) return;
  const ms = Date.now() - current.start;
  const { day, late } = mode;
  const i = current.roundIndex;
  const round = current.data.rounds[i];
  const correct = current.pick === round.fake;
  const points = roundScore(correct, ms);
  current.done = true;
  clearInterval(current.timer);
  store.saveRound(day, late, i, { pick: current.pick, ms, points, correct });
  revealRound(round, current.pick, points);
  // record on the leaderboard (server re-judges and recomputes the points)
  if (api.enabled()) {
    const name = api.savedName();
    api.submitRound({ day, round: i, pick: current.pick, ms, name })
      .then(() => renderBoard())
      .catch((e) => showError('round-error', `Couldn't save this round to the leaderboard: ${e.message}`));
  }
}

function sourcesLine(sources) {
  const s = el('span', { class: 'fact-sources' }, 'Source: ');
  sources.slice(0, 3).forEach((src, k) => {
    if (k) s.append(', ');
    s.append(el('a', { href: src.url, target: '_blank', rel: 'noopener', text: src.title }));
  });
  return s;
}

function revealRound(round, pick, points) {
  const items = [...$('facts').querySelectorAll('.fact')];
  items.forEach((b, k) => {
    b.disabled = true;
    b.style.setProperty('--jgg-i', k); // the tags and sources reveal one card after another
    const isFake = k === round.fake;
    b.classList.add(isFake ? 'is-fake' : 'is-true');
    if (isFake && k === pick) b.classList.add('picked-right');
    const tags = [];
    tags.push(el('span', { class: `fact-tag ${isFake ? 'fake' : 'true'}`, text: isFake ? 'Fake' : 'True' }));
    if (k === pick) tags.push(el('span', { class: 'fact-tag yours', text: 'Your pick' }));
    b.prepend(...tags);
    b.append(sourcesLine(round.facts[k].sources));
  });
  $('confirm').hidden = true;
  $('round-question').textContent = pick === round.fake ? 'Correct!' : 'Not quite.';
  const sc = $('round-score');
  countUp(sc, points);
  sc.className = `score ${points > 0 ? 'good' : 'bad'}`;

  // the original sentence with the changed detail marked
  const o = round.original, c = round.change;
  const orig = $('original');
  orig.replaceChildren(
    el('span', { class: 'label', text: 'The real fact' }),
    o.slice(0, c.start), el('mark', { text: o.slice(c.start, c.end) }), o.slice(c.end),
    el('span', { class: 'fact-sources' }, 'The fake said ', el('del', { text: c.new }), ' instead.'),
  );

  const body = `Day: ${mode.day} (Factle #${dayNumber(mode.day)}), round ${current.roundIndex + 1}\n\n` +
    `Fake shown: ${round.facts[round.fake].text}\n\nOriginal: ${round.original}\n\n` +
    `Why it's actually true (a link helps):\n`;
  $('report').href = `${REPO}/issues/new?labels=reported-fake&title=${encodeURIComponent(`Fake is actually true: ${mode.day} round ${current.roundIndex + 1}`)}&body=${encodeURIComponent(body)}`;
  $('next').textContent = current.roundIndex + 1 < ROUNDS ? 'Next round →' : 'See your score →';
  show('reveal', true);
  scrollTo($('reveal'), 'nearest');
}

function nextRound() {
  const i = current.roundIndex + 1;
  current = null;
  if (i < ROUNDS) startRound(i);
  else { renderDone(true); renderBoard(); scrollTo($('card')); }
}

// fresh: just finished round 5, so the score counts up and the rows come in. Never on a reload or re-render.
function renderDone(fresh) {
  const { day, late } = mode;
  const rounds = store.progress(day, late).rounds;
  const total = rounds.reduce((a, r) => a + (r?.points || 0), 0);
  fresh ? phase($('round'), $('done')) : show('done', true);
  $('daily-score-caption').textContent = late ? `Your replay of ${day}` : "Today's score";
  if (fresh) countUp($('daily-score'), total); else $('daily-score').textContent = total;
  const list = $('round-list');
  list.replaceChildren(...rounds.map((r, i) => el('li', { class: `attempt-row${fresh ? ' is-new' : ''}`, style: `--jgg-i: ${i}` },
    el('div', { class: 'attempt-head' },
      el('span', { class: 'attempt-label', text: `${roundEmoji(r.points)} Round ${i + 1}${r.correct ? ` · ${(r.ms / 1000).toFixed(1)} s` : ' · wrong pick'}` }),
      el('span', { class: `attempt-score ${r.points > 0 ? 'good' : 'bad'}`, text: String(r.points) })))));
  show('share-done', false);
  window.JGG?.rate({ game: 'factle', day, mount: $('rate') });
}

function shareText() {
  const { day, late } = mode;
  const rounds = store.progress(day, late).rounds;
  const total = rounds.reduce((a, r) => a + (r?.points || 0), 0);
  const streak = late ? 0 : store.streak(todayKey(), addDays, ROUNDS);
  return `Factle #${dayNumber(day)}${late ? ' (replay)' : ''}: ${total}/500\n${rounds.map((r) => roundEmoji(r.points)).join('')}` +
    `${streak > 1 ? `  🔥${streak}` : ''}\n${SITE}`;
}

async function share() {
  const text = shareText();
  try {
    if (navigator.share && matchMedia('(pointer: coarse)').matches) { await navigator.share({ text }); return; }
    await navigator.clipboard.writeText(text);
    show('share-done', true);
  } catch {
    prompt('Copy your result:', text);
  }
}

// --- leaderboard ----------------------------------------------------------------------------------

async function renderBoard() {
  if (!api.enabled()) { show('board', false); return; }
  const { day, late } = mode;
  show('board', true);
  $('board').querySelector('h2').textContent = late ? `Played later: ${day}` : "Today's leaderboard";
  let b;
  try { b = await api.board(day, late); }
  catch (e) { $('board-note').textContent = `Leaderboard unavailable: ${e.message}`; show('board-note', true); return; }
  show('board-note', false);
  $('players').textContent = b.players ? `${b.players} player${b.players === 1 ? '' : 's'}` : '';
  const rows = [...b.top];
  if (b.you) rows.push(null, b.you);
  $('rows').replaceChildren(...rows.map((r) => r === null ? el('li', { class: 'row-gap', text: '···' })
    : el('li', { class: `row${r.you ? ' me' : ''}` },
      el('span', { class: 'row-rank', text: `${r.rank}` }),
      el('div', { class: 'row-main' },
        el('div', { class: 'row-name', text: r.name, title: r.name ?? '', dir: 'auto' }),
        el('div', { class: 'row-sub' },
          el('span', { class: 'row-emoji', text: (r.rounds || []).map(roundEmoji).join('') }),
          r.played < ROUNDS ? ` · ${r.played}/${ROUNDS} rounds` : '')),
      el('span', { class: 'row-score', text: String(r.total ?? '') }))));
  show('board-empty', !b.top.length);
}

// --- archive --------------------------------------------------------------------------------------

async function browseArchive() {
  const list = $('archive-list');
  if (!list.hidden) { list.hidden = true; return; }
  const today = todayKey();
  const items = [];
  for (let d = addDays(today, -1); index && d >= index.first; d = addDays(d, -1)) items.push(d);
  let summary = {};
  try { if (api.enabled() && items.length) summary = (await api.days(items[items.length - 1], items[0])).days || {}; }
  catch { /* the list works without counts */ }
  list.replaceChildren(...(items.length ? items.map((d) => {
    const s = summary[d];
    const mine = doneCount(d, false) >= ROUNDS ? store.progress(d).rounds.reduce((a, r) => a + r.points, 0)
      : doneCount(d, true) >= ROUNDS ? store.progress(d, true).rounds.reduce((a, r) => a + r.points, 0) : null;
    return el('li', {}, el('button', { class: 'archive-list-item', type: 'button', onclick: () => openArchive(d) },
      el('span', { class: 'archive-list-day', text: `Factle #${dayNumber(d)} · ${d}` }),
      el('span', { class: 'archive-list-prompt', text: [
        s?.players ? `${s.players} played on the day, best ${s.top}` : 'Nobody played on the day',
        mine !== null ? `you: ${mine}` : null].filter(Boolean).join(' · ') })));
  }) : [el('li', { class: 'archive-list-empty', text: 'No past days yet. Factle started today.' })]));
  list.hidden = false;
}

function openArchive(d) {
  if (current) { clearInterval(current.timer); current = null; }
  // a day you already finished on the day itself is shown as done; otherwise it's a replay
  mode = doneCount(d, false) >= ROUNDS ? { day: d, late: false } : { day: d, late: true };
  $('archive-list').hidden = true;
  render();
  scrollTo($('card'));
}

// --- errors ---------------------------------------------------------------------------------------

function showError(id, msg) { $(id).textContent = msg; show(id, true); }
function hideError(id) { show(id, false); }

// --- boot -----------------------------------------------------------------------------------------

$('start-form').addEventListener('submit', (e) => {
  e.preventDefault();
  hideError('start-error');
  const name = ($('name').value || api.savedName()).replace(/\s+/g, ' ').trim();
  if (!name) { showError('start-error', 'Enter a name for the leaderboard.'); return; }
  api.saveName(name.slice(0, 20));
  startRound(doneCount(mode.day, mode.late));
});
$('confirm').addEventListener('click', confirmPick);
$('next').addEventListener('click', nextRound);
$('share').addEventListener('click', share);
$('archive-browse').addEventListener('click', browseArchive);

(async function boot() {
  await api.loadConfig();
  try { index = await (await fetch('data/index.json', { cache: 'no-cache' })).json(); } catch { index = null; }
  const q = new URLSearchParams(location.search).get('day');
  if (q && index && q >= index.first && q < todayKey()) openArchive(q);
  else render();
  tickCountdown();
  setInterval(tickCountdown, 1000);
})();
