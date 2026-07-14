-- ============================================
-- NOTES (Faza 17 — strumień notatek: insight/decision/reminder/idea)
-- ============================================

-- name: add<!
INSERT INTO notes (date, category, content, related_task_id, related_run_id,
                   related_session_id, source)
VALUES (:date, :category, :content, :related_task_id, :related_run_id,
        :related_session_id, COALESCE(:source, 'chat'));


-- name: get^
SELECT * FROM notes WHERE id = :id;


-- name: recent
-- Ostatnie N notatek — feed na dashboardzie.
SELECT *
  FROM notes
 ORDER BY date DESC, id DESC
 LIMIT :limit;


-- name: by_category
SELECT *
  FROM notes
 WHERE category = :category
 ORDER BY date DESC, id DESC
 LIMIT :limit;


-- name: for_task
SELECT *
  FROM notes
 WHERE related_task_id = :task_id
 ORDER BY date DESC, id DESC;


-- name: for_run
SELECT *
  FROM notes
 WHERE related_run_id = :run_id
 ORDER BY date DESC, id DESC;


-- name: delete!
DELETE FROM notes WHERE id = :id;
