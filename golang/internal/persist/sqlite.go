package persist

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"time"

	_ "modernc.org/sqlite"
)

// DB SQLite 封装：users / knowledge_states / refresh_tokens / events / submissions / audit_logs。
type DB struct {
	SQL *sql.DB
}

// Open 打开 SQLite。path 为空时使用 ./data/edu.db；设为 ":memory:" 则用内存库。
func Open(path string) (*DB, error) {
	if path == "" {
		path = filepath.Join("data", "edu.db")
	}
	if path != ":memory:" {
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			return nil, fmt.Errorf("mkdir persist dir: %w", err)
		}
	}
	sqlDB, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, err
	}
	sqlDB.SetMaxOpenConns(1)
	if _, err := sqlDB.Exec(`PRAGMA foreign_keys = ON`); err != nil {
		_ = sqlDB.Close()
		return nil, err
	}
	db := &DB{SQL: sqlDB}
	if err := db.migrate(); err != nil {
		_ = sqlDB.Close()
		return nil, err
	}
	return db, nil
}

func (db *DB) Close() error {
	if db == nil || db.SQL == nil {
		return nil
	}
	return db.SQL.Close()
}

func (db *DB) migrate() error {
	_, err := db.SQL.Exec(`
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL,
  tenant_id TEXT NOT NULL DEFAULT '1',
  learner_id TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_states (
  learner_id TEXT NOT NULL,
  knowledge_id TEXT NOT NULL,
  mastery REAL NOT NULL DEFAULT 0.1,
  attempts INTEGER NOT NULL DEFAULT 0,
  correct_count INTEGER NOT NULL DEFAULT 0,
  streak INTEGER NOT NULL DEFAULT 0,
  last_attempt TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (learner_id, knowledge_id)
);
CREATE TABLE IF NOT EXISTS refresh_tokens (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revoked INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_refresh_user ON refresh_tokens(user_id);
CREATE TABLE IF NOT EXISTS events (
  public_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT '1',
  type TEXT NOT NULL,
  source TEXT NOT NULL,
  learner_public_id TEXT NOT NULL,
  data_json TEXT NOT NULL DEFAULT '{}',
  correlation_id TEXT,
  timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_events_learner ON events(learner_public_id);
CREATE TABLE IF NOT EXISTS submissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL DEFAULT '1',
  learner_id TEXT NOT NULL,
  knowledge_id TEXT NOT NULL,
  is_correct INTEGER NOT NULL,
  time_spent_seconds REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_submissions_learner ON submissions(learner_id, knowledge_id);
CREATE TABLE IF NOT EXISTS audit_logs (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT '1',
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  target TEXT NOT NULL,
  ip TEXT,
  user_agent TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  prev_hash TEXT,
  curr_hash TEXT NOT NULL
);
`)
	if err != nil {
		return err
	}
	if err := db.migrateBiz(); err != nil {
		return err
	}
	return db.migrateCritiques()
}

func nowRFC3339() string {
	return time.Now().UTC().Format(time.RFC3339Nano)
}

func nullStr(s string) any {
	if s == "" {
		return nil
	}
	return s
}
