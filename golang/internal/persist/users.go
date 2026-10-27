package persist

import (
	"fmt"
	"time"

	"multi-agent-education/golang/internal/auth"
)

// LoadUsers 从 SQLite 加载全部用户到 UserStore。
func (db *DB) LoadUsers(store *auth.UserStore) error {
	rows, err := db.SQL.Query(`SELECT id, email, password_hash, role, tenant_id, learner_id, created_at FROM users`)
	if err != nil {
		return err
	}
	defer rows.Close()
	for rows.Next() {
		var u auth.User
		var created string
		var role string
		if err := rows.Scan(&u.ID, &u.Email, &u.PasswordHash, &role, &u.TenantID, &u.LearnerID, &created); err != nil {
			return err
		}
		u.Role = auth.Role(role)
		if t, err := time.Parse(time.RFC3339Nano, created); err == nil {
			u.CreatedAt = t
		} else {
			u.CreatedAt = time.Now()
		}
		if err := store.ImportUser(&u); err != nil {
			return err
		}
	}
	return rows.Err()
}

// SaveUser upsert 用户。
func (db *DB) SaveUser(u *auth.User) error {
	_, err := db.SQL.Exec(`
INSERT INTO users (id, email, password_hash, role, tenant_id, learner_id, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
  email=excluded.email,
  password_hash=excluded.password_hash,
  role=excluded.role,
  tenant_id=excluded.tenant_id,
  learner_id=excluded.learner_id
`, u.ID, u.Email, u.PasswordHash, string(u.Role), u.TenantID, u.LearnerID, u.CreatedAt.UTC().Format(time.RFC3339Nano))
	return err
}

// SeedDemoUsers 写入演示账号（若不存在）。
func (db *DB) SeedDemoUsers(store *auth.UserStore) error {
	demos := []struct {
		email string
		role  auth.Role
	}{
		{"student@demo.com", auth.RoleStudent},
		{"teacher@demo.com", auth.RoleTeacher},
		{"admin@demo.com", auth.RoleAdmin},
	}
	hash, err := auth.HashPassword("demo123456")
	if err != nil {
		return err
	}
	for _, d := range demos {
		if _, ok := store.GetUserByEmail(d.email); ok {
			continue
		}
		u, err := store.CreateUser(d.email, hash, d.role, "1")
		if err != nil {
			return fmt.Errorf("seed %s: %w", d.email, err)
		}
		if err := db.SaveUser(u); err != nil {
			return err
		}
	}
	return nil
}
