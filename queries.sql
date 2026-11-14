-- Named DuckDB queries. Each block starts with "-- name: <name>"; parameters use $name.

-- name: margins
-- Average margin (overround) per bookmaker and snapshot, ranked tightest first.
-- Caveat: bookmakers cover different seasons (see seasons column), and margins drift over
-- time, so a ranking across books is only roughly like-for-like.
WITH per_row AS (
    SELECT o.bookmaker, o.snapshot, m.season,
           1 / o.odds_h + 1 / o.odds_d + 1 / o.odds_a - 1 AS margin
    FROM odds_snapshots o
    JOIN matches m USING (match_id)
)
SELECT bookmaker,
       snapshot,
       count(*)                          AS n_matches,
       string_agg(DISTINCT season, ',' ORDER BY season) AS seasons,
       round(avg(margin) * 100, 2)       AS avg_margin_pct,
       round(median(margin) * 100, 2)    AS median_margin_pct,
       round(min(margin) * 100, 2)       AS min_margin_pct,
       RANK() OVER (PARTITION BY snapshot ORDER BY avg(margin)) AS rank_tightest
FROM per_row
GROUP BY bookmaker, snapshot
ORDER BY snapshot DESC, rank_tightest;

-- name: moves
-- Largest price moves from the 'open' (pre-closing) to the 'close' snapshot, per match,
-- bookmaker and outcome, using LAG() over the snapshots in time order.
-- Moves are measured in margin-free probability (proportional de-vig of each snapshot),
-- so a book simply changing its overround does not show up as a move.
-- HONESTY NOTE: with only two snapshots per match this is a crude PROXY for a "steam move".
-- Real steam detection needs timestamped tick data (how fast, across how many books at once).
-- The same LAG() query would work unchanged on tick data: it compares consecutive rows.
WITH snaps AS (
    SELECT match_id, bookmaker, odds_h, odds_d, odds_a,
           CASE snapshot WHEN 'open' THEN 0 ELSE 1 END AS snap_order,
           1 / odds_h + 1 / odds_d + 1 / odds_a      AS book_sum
    FROM odds_snapshots
),
by_outcome AS (
    SELECT match_id, bookmaker, snap_order, 'H' AS outcome, odds_h AS odds,
           (1 / odds_h) / book_sum AS fair_prob FROM snaps
    UNION ALL
    SELECT match_id, bookmaker, snap_order, 'D', odds_d, (1 / odds_d) / book_sum FROM snaps
    UNION ALL
    SELECT match_id, bookmaker, snap_order, 'A', odds_a, (1 / odds_a) / book_sum FROM snaps
),
with_prev AS (
    SELECT *,
           LAG(odds)      OVER w AS prev_odds,
           LAG(fair_prob) OVER w AS prev_prob
    FROM by_outcome
    WINDOW w AS (PARTITION BY match_id, bookmaker, outcome ORDER BY snap_order)
)
SELECT m.match_date,
       m.home,
       m.away,
       p.bookmaker,
       p.outcome,
       p.prev_odds                                AS open_odds,
       p.odds                                     AS close_odds,
       round((p.fair_prob - p.prev_prob) * 100, 2) AS prob_move_pp,
       m.result
FROM with_prev p
JOIN matches m USING (match_id)
WHERE p.prev_odds IS NOT NULL                       -- needs both snapshots
  AND (CAST($bookmaker AS VARCHAR) IS NULL OR p.bookmaker = $bookmaker)
ORDER BY abs(p.fair_prob - p.prev_prob) DESC, m.match_date, p.bookmaker, p.outcome
LIMIT $limit;

-- name: odds_with_matches
-- Odds joined with match info: the input for the detector and calibration.
SELECT o.match_id, m.season, m.match_date, m.home, m.away, m.result,
       o.bookmaker, o.snapshot, o.odds_h, o.odds_d, o.odds_a
FROM odds_snapshots o
JOIN matches m USING (match_id)
ORDER BY m.match_date, o.match_id, o.snapshot, o.bookmaker;
