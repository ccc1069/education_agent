package persist

import (
	"database/sql"
	"encoding/json"
	"time"

	"multi-agent-education/golang/internal/audit"
	"multi-agent-education/golang/internal/auth"
	"multi-agent-education/golang/internal/eventbus"
)

// SaveRefreshToken upsert 刷新令牌。
func (db *DB) SaveRefreshToken(rt *auth.RefreshToken) error {
	revoked := 0
	if rt.Revoked {
		revoked = 1
	}
	_, err := db.SQL.Exec(`
INSERT INTO refresh_tokens (token_hash, user_id, expires_at, created_at, revoked)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(token_hash) DO UPDATE SET
  revoked=excluded.revoked,
  expires_at=excluded.expires_at
`, rt.TokenHash, rt.UserID,
		rt.ExpiresAt.UTC().Format(time.RFC3339Nano),
		rt.CreatedAt.UTC().Format(time.RFC3339Nano),
		revoked)
	return err
}

// LoadRefreshTokens 启动时灌入 RefreshTokenStore。
func (db *DB) LoadRefreshTokens(store *auth.RefreshTokenStore) error {
	rows, err := db.SQL.Query(`SELECT token_hash, user_id, expires_at, created_at, revoked FROM refresh_tokens`)
	if err != nil {
		return err
	}
	defer rows.Close()
	for rows.Next() {
		var rt auth.RefreshToken
		var exp, created string
		var revoked int
		if err := rows.Scan(&rt.TokenHash, &rt.UserID, &exp, &created, &revoked); err != nil {
			return err
		}
		rt.Revoked = revoked != 0
		if t, err := time.Parse(time.RFC3339Nano, exp); err == nil {
			rt.ExpiresAt = t
		}
		if t, err := time.Parse(time.RFC3339Nano, created); err == nil {
			rt.CreatedAt = t
		}
		store.ImportToken(&rt)
	}
	return rows.Err()
}

// AppendEvent 追加事件溯源行。
func (db *DB) AppendEvent(e eventbus.Event) error {
	data, _ := json.Marshal(e.Data)
	if data == nil {
		data = []byte("{}")
	}
	_, err := db.SQL.Exec(`
INSERT OR REPLACE INTO events (
  public_id, tenant_id, type, source, learner_public_id, data_json, correlation_id, timestamp
) VALUES (?, '1', ?, ?, ?, ?, ?, ?)`,
		e.ID, string(e.Type), e.Source, e.LearnerID, string(data), nullStr(e.CorrelationID),
		e.Timestamp.UTC().Format(time.RFC3339Nano))
	return err
}

// RecordSubmission 追加答题记录。
func (db *DB) RecordSubmission(learnerID, knowledgeID string, isCorrect bool, timeSpent float64) error {
	correct := 0
	if isCorrect {
		correct = 1
	}
	_, err := db.SQL.Exec(`
INSERT INTO submissions (tenant_id, learner_id, knowledge_id, is_correct, time_spent_seconds, created_at)
VALUES ('1', ?, ?, ?, ?, ?)`,
		learnerID, knowledgeID, correct, timeSpent, nowRFC3339())
	return err
}

// AppendAuditLog 写入审计链。
func (db *DB) AppendAuditLog(log *audit.AuditLog) error {
	meta, _ := json.Marshal(log.Metadata)
	if meta == nil {
		meta = []byte("{}")
	}
	_, err := db.SQL.Exec(`
INSERT OR REPLACE INTO audit_logs (
  id, tenant_id, actor, action, target, ip, user_agent, metadata_json, created_at, prev_hash, curr_hash
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		log.ID, log.TenantID, log.Actor, log.Action, log.Target, log.IP, log.UserAgent,
		string(meta), log.Timestamp.UTC().Format(time.RFC3339Nano), log.PrevHash, log.CurrHash)
	return err
}

// LoadAuditTail 取链尾 curr_hash，供 AuditService 续写。
func (db *DB) LoadAuditTail() (string, error) {
	var hash string
	err := db.SQL.QueryRow(`SELECT curr_hash FROM audit_logs ORDER BY created_at DESC LIMIT 1`).Scan(&hash)
	if err == sql.ErrNoRows {
		return "", nil
	}
	return hash, err
}
