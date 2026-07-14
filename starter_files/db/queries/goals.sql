-- ============================================
-- WEEKLY GOALS (Faza 17 — cel per kategoria per tydzień)
-- ============================================

-- name: upsert!
-- Jeden goal per (week_start, category). Ponowny insert dla tej pary nadpisuje.
INSERT INTO weekly_goals (week_start, category, goal, status)
VALUES (:week_start, :category, :goal, COALESCE(:status, 'open'))
ON CONFLICT(week_start, category) DO UPDATE SET
    goal = excluded.goal,
    status = excluded.status,
    updated_at = datetime('now');


-- name: for_week
SELECT *
  FROM weekly_goals
 WHERE week_start = :week_start
 ORDER BY category;


-- name: recent
-- Ostatnie N tygodni per kategoria — do wykresu / historii.
SELECT *
  FROM weekly_goals
 ORDER BY week_start DESC, category
 LIMIT :limit;


-- name: mark_done!
UPDATE weekly_goals
   SET status = 'done',
       updated_at = datetime('now')
 WHERE id = :id;


-- name: reopen!
UPDATE weekly_goals
   SET status = 'open',
       updated_at = datetime('now')
 WHERE id = :id;


-- name: delete!
DELETE FROM weekly_goals WHERE id = :id;
