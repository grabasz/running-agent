-- ============================================
-- TASKS (Faza 17 — hierarchiczna lista SMART)
-- ============================================

-- name: add<!
INSERT INTO tasks (parent_id, category, title, description, success_criteria,
                   due_date, priority, status)
VALUES (:parent_id, :category, :title, :description, :success_criteria,
        :due_date, :priority, COALESCE(:status, 'open'));


-- name: get^
SELECT * FROM tasks WHERE id = :id;


-- name: list_open
-- Otwarte taski. NULLS LAST na due_date żeby zadania bez terminu były na końcu.
SELECT *
  FROM tasks
 WHERE status = 'open'
 ORDER BY (due_date IS NULL), due_date, id;


-- name: list_by_category
SELECT *
  FROM tasks
 WHERE category = :category
   AND status != 'wontdo'
 ORDER BY (status = 'done'), (due_date IS NULL), due_date, id;


-- name: list_all
-- Wszystkie taski (open + done + wontdo), dla widoku drzewa "pokaż wszystko".
SELECT *
  FROM tasks
 ORDER BY (parent_id IS NULL) DESC, parent_id, (due_date IS NULL), due_date, id;


-- name: children
SELECT *
  FROM tasks
 WHERE parent_id = :parent_id
 ORDER BY (status = 'done'), (due_date IS NULL), due_date, id;


-- name: roots
-- Root tasks (parent_id NULL) — projekty lub samodzielne zadania.
SELECT *
  FROM tasks
 WHERE parent_id IS NULL
 ORDER BY (status = 'done'), (due_date IS NULL), due_date, id;


-- name: mark_done!
UPDATE tasks
   SET status = 'done',
       done_at = datetime('now'),
       updated_at = datetime('now')
 WHERE id = :id;


-- name: reopen!
UPDATE tasks
   SET status = 'open',
       done_at = NULL,
       updated_at = datetime('now')
 WHERE id = :id;


-- name: mark_wontdo!
UPDATE tasks
   SET status = 'wontdo',
       updated_at = datetime('now')
 WHERE id = :id;


-- name: update!
-- Edytuj dowolne pola. Przekaż NULL dla pól które chcesz zachować bez zmian —
-- COALESCE(:x, x) zachowuje starą wartość gdy nowa = NULL.
-- WAŻNE: jeśli chcesz *wyczyścić* pole na NULL (np. usunąć due_date), użyj
-- clear_due lub innej celowanej mutation. Ten update nie potrafi "unset".
UPDATE tasks
   SET title            = COALESCE(:title, title),
       description      = COALESCE(:description, description),
       success_criteria = COALESCE(:success_criteria, success_criteria),
       due_date         = COALESCE(:due_date, due_date),
       category         = COALESCE(:category, category),
       priority         = COALESCE(:priority, priority),
       parent_id        = COALESCE(:parent_id, parent_id),
       updated_at       = datetime('now')
 WHERE id = :id;


-- name: clear_due!
UPDATE tasks SET due_date = NULL, updated_at = datetime('now') WHERE id = :id;


-- name: delete!
DELETE FROM tasks WHERE id = :id;
