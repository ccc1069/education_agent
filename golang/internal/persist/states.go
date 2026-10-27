package persist

import (
	"database/sql"
	"fmt"
	"time"

	"multi-agent-education/golang/internal/model"
)

// StateRow 持久化行
type StateRow struct {
	LearnerID    string
	KnowledgeID  string
	Mastery      float64
	Attempts     int
	CorrectCount int
	Streak       int
	LastAttempt  *time.Time
	Version      int
}

// LoadStates 加载某学习者全部 knowledge_states。
func (db *DB) LoadStates(learnerID string) ([]StateRow, error) {
	rows, err := db.SQL.Query(`
SELECT knowledge_id, mastery, attempts, correct_count, streak, last_attempt, version
FROM knowledge_states WHERE learner_id = ?`, learnerID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []StateRow
	for rows.Next() {
		var r StateRow
		r.LearnerID = learnerID
		var last sql.NullString
		if err := rows.Scan(&r.KnowledgeID, &r.Mastery, &r.Attempts, &r.CorrectCount, &r.Streak, &last, &r.Version); err != nil {
			return nil, err
		}
		if last.Valid && last.String != "" {
			if t, err := time.Parse(time.RFC3339Nano, last.String); err == nil {
				r.LastAttempt = &t
			}
		}
		out = append(out, r)
	}
	return out, rows.Err()
}

// Hydrate 从 DB 填充 LearnerModel。
func (db *DB) Hydrate(m *model.LearnerModel) error {
	rows, err := db.LoadStates(m.LearnerID)
	if err != nil {
		return err
	}
	ApplyStates(m, rows)
	return nil
}

// Save 同 SaveLearnerModel。
func (db *DB) Save(m *model.LearnerModel) error {
	return db.SaveLearnerModel(m)
}

// SaveLearnerModel CAS upsert：UPDATE ... WHERE version=?；冲突则刷新 version 重试。
func (db *DB) SaveLearnerModel(m *model.LearnerModel) error {
	states := m.GetAllStates()
	for i := range states {
		if err := db.casSaveState(m.LearnerID, &states[i]); err != nil {
			return err
		}
		// 回写 version 到模型
		m.PutState(&states[i])
	}
	return nil
}

func (db *DB) casSaveState(learnerID string, s *model.KnowledgeState) error {
	var last any
	if !s.LastAttempt.IsZero() {
		last = s.LastAttempt.UTC().Format(time.RFC3339Nano)
	}
	for attempt := 0; attempt < 3; attempt++ {
		var dbVersion int
		err := db.SQL.QueryRow(
			`SELECT version FROM knowledge_states WHERE learner_id=? AND knowledge_id=?`,
			learnerID, s.KnowledgeID,
		).Scan(&dbVersion)

		if err == sql.ErrNoRows {
			_, err = db.SQL.Exec(`
INSERT INTO knowledge_states (
  learner_id, knowledge_id, mastery, attempts, correct_count, streak, last_attempt, version, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)`,
				learnerID, s.KnowledgeID, s.Mastery, s.Attempts, s.CorrectCount, s.Streak, last, nowRFC3339())
			if err != nil {
				continue // 并发插入
			}
			s.Version = 1
			return nil
		}
		if err != nil {
			return err
		}

		expected := s.Version
		if expected <= 0 {
			expected = dbVersion
		}
		res, err := db.SQL.Exec(`
UPDATE knowledge_states SET
  mastery=?, attempts=?, correct_count=?, streak=?, last_attempt=?, version=?, updated_at=?
WHERE learner_id=? AND knowledge_id=? AND version=?`,
			s.Mastery, s.Attempts, s.CorrectCount, s.Streak, last, expected+1, nowRFC3339(),
			learnerID, s.KnowledgeID, expected)
		if err != nil {
			return err
		}
		n, _ := res.RowsAffected()
		if n > 0 {
			s.Version = expected + 1
			return nil
		}
		s.Version = dbVersion
	}
	return fmt.Errorf("CAS failed learner=%s kp=%s", learnerID, s.KnowledgeID)
}

// ApplyStates 把行写入 LearnerModel。
func ApplyStates(m *model.LearnerModel, rows []StateRow) {
	for _, r := range rows {
		st := &model.KnowledgeState{
			KnowledgeID:  r.KnowledgeID,
			Mastery:      r.Mastery,
			Attempts:     r.Attempts,
			CorrectCount: r.CorrectCount,
			Streak:       r.Streak,
			Version:      r.Version,
		}
		if r.LastAttempt != nil {
			st.LastAttempt = *r.LastAttempt
		}
		m.PutState(st)
	}
}
