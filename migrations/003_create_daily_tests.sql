-- Daily tests and streak completion history
-- depends: 002_create_initial_admin

CREATE TABLE daily_tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    completed_on TEXT NOT NULL,
    UNIQUE(user_id, completed_on)
);
