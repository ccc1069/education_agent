package persist

import (
	"encoding/json"
)

// CritiqueRow Critic 评估落盘行（对齐 Python critiques / Java Critique）。
type CritiqueRow struct {
	LearnerID            string
	KnowledgeID          string
	TeachingEventID      string
	Overall              int
	Scores               map[string]float64
	Critique             string
	NeedsRegeneration    bool
	Regenerated          bool
	OriginalResponse     string
	RegeneratedResponse  string
	CriticModel          string
	CriticTokens         int
	TenantID             string
}

func (db *DB) migrateCritiques() error {
	_, err := db.SQL.Exec(`
CREATE TABLE IF NOT EXISTS critiques (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  learner_id TEXT NOT NULL,
  knowledge_id TEXT NOT NULL,
  teaching_event_id TEXT,
  overall INTEGER NOT NULL,
  scores_json TEXT NOT NULL DEFAULT '{}',
  critique TEXT NOT NULL,
  needs_regeneration INTEGER NOT NULL DEFAULT 0,
  regenerated INTEGER NOT NULL DEFAULT 0,
  original_response TEXT NOT NULL,
  regenerated_response TEXT,
  critic_model TEXT,
  critic_tokens INTEGER NOT NULL DEFAULT 0,
  tenant_id TEXT NOT NULL DEFAULT '1',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_critiques_learner ON critiques(learner_id);
CREATE INDEX IF NOT EXISTS ix_critiques_knowledge ON critiques(knowledge_id);
CREATE INDEX IF NOT EXISTS ix_critiques_teaching_event ON critiques(teaching_event_id);
`)
	return err
}

// InsertCritique 写入一条评估记录，返回自增 id。
func (db *DB) InsertCritique(row CritiqueRow) (int64, error) {
	scores, _ := json.Marshal(row.Scores)
	if scores == nil {
		scores = []byte("{}")
	}
	needs := 0
	if row.NeedsRegeneration {
		needs = 1
	}
	regen := 0
	if row.Regenerated {
		regen = 1
	}
	tenant := row.TenantID
	if tenant == "" {
		tenant = "1"
	}
	res, err := db.SQL.Exec(`
INSERT INTO critiques (
  learner_id, knowledge_id, teaching_event_id, overall, scores_json, critique,
  needs_regeneration, regenerated, original_response, regenerated_response,
  critic_model, critic_tokens, tenant_id, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		row.LearnerID, row.KnowledgeID, nullStr(row.TeachingEventID), row.Overall,
		string(scores), row.Critique, needs, regen, row.OriginalResponse,
		nullStr(row.RegeneratedResponse), nullStr(row.CriticModel), row.CriticTokens,
		tenant, nowRFC3339())
	if err != nil {
		return 0, err
	}
	return res.LastInsertId()
}

// MarkCritiqueRegenerated 按 teaching_event_id 回写重生成结果。
func (db *DB) MarkCritiqueRegenerated(teachingEventID, regeneratedResponse string) error {
	_, err := db.SQL.Exec(`
UPDATE critiques SET regenerated=1, regenerated_response=?
WHERE teaching_event_id=?`, regeneratedResponse, teachingEventID)
	return err
}

// CountCritiques 测试/健康检查用。
func (db *DB) CountCritiques() (int, error) {
	var n int
	err := db.SQL.QueryRow(`SELECT COUNT(*) FROM critiques`).Scan(&n)
	return n, err
}
