-- D1 schema for Factle's shared daily leaderboard.
-- The browser sends only (day, round, pick, time taken). The worker judges the pick against its own copy of the
-- answers (site/data/index.json, bundled at deploy) and computes the points itself (site/js/daily.js).

CREATE TABLE IF NOT EXISTS players (
  id         TEXT PRIMARY KEY,   -- server-generated UUID
  token_hash TEXT NOT NULL,      -- SHA-256 of a server-issued session token
  created_at TEXT NOT NULL
);

-- One row per (player, day, board, round). Insert-only: the first pick counts.
CREATE TABLE IF NOT EXISTS picks (
  id           TEXT PRIMARY KEY,
  player_id    TEXT NOT NULL REFERENCES players (id),
  day_key      TEXT NOT NULL,                       -- puzzle's UTC day, YYYY-MM-DD
  is_late      INTEGER NOT NULL DEFAULT 0,          -- 1 = replayed from the archive after its day
  round        INTEGER NOT NULL CHECK (round >= 0 AND round < 5),
  pick         INTEGER NOT NULL CHECK (pick >= 0 AND pick < 5),
  ms           INTEGER NOT NULL CHECK (ms > 0),
  correct      INTEGER NOT NULL,
  points       INTEGER NOT NULL CHECK (points >= 0 AND points <= 100),
  submitted_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS picks_player_round ON picks (player_id, day_key, is_late, round);

-- Running totals per player per day/board, so a leaderboard view reads ~20 rows instead of every pick
-- (D1 free plan: 5M rows read/day).
CREATE TABLE IF NOT EXISTS totals (
  player_id    TEXT NOT NULL,
  day_key      TEXT NOT NULL,
  is_late      INTEGER NOT NULL,
  display_name TEXT NOT NULL,
  total        INTEGER NOT NULL,
  played       INTEGER NOT NULL,
  rounds       TEXT NOT NULL,     -- comma-separated points per round, in order
  last_at      TEXT NOT NULL,
  PRIMARY KEY (player_id, day_key, is_late)
);
CREATE INDEX IF NOT EXISTS totals_board ON totals (day_key, is_late, total DESC, last_at ASC);

-- Per-day counters for the board header and the archive list.
CREATE TABLE IF NOT EXISTS day_stats (
  day_key TEXT NOT NULL,
  is_late INTEGER NOT NULL,
  players INTEGER NOT NULL,
  top     INTEGER NOT NULL,
  PRIMARY KEY (day_key, is_late)
);
