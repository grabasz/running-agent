-- ============================================
-- WEEKLY GOALS (Faza 17 — cel per kategoria per tydzień)
-- ============================================

-- name: upsert!
-- Jeden goal per (user_id, week_start, category). Ponowny insert dla tej trójki nadpisuje.
INSERT INTO weekly_goals (user_id, week_start, category, goal, status)
VALUES (:user_id, :week_start, :category, :goal, COALESCE(:status, 'open'))
ON CONFLICT(user_id, week_start, category) DO UPDATE SET
    goal = excluded.goal,
    status = excluded.status,
    updated_at = datetime('now');


-- name: for_week
SELECT *
  FROM weekly_goals
 WHERE week_start = :week_start
   AND user_id = COALESCE(:user_id, 1)
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
