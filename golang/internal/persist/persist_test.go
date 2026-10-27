package persist_test

import (
	"path/filepath"
	"testing"

	"multi-agent-education/golang/internal/agent"
	"multi-agent-education/golang/internal/auth"
	"multi-agent-education/golang/internal/eventbus"
	"multi-agent-education/golang/internal/persist"
)

func TestSQLiteUsersAndMastery(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "edu.db")
	db, err := persist.Open(path)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	defer db.Close()

	store := auth.NewUserStore()
	store.SetPersistHook(func(u *auth.User) error { return db.SaveUser(u) })
	if err := db.SeedDemoUsers(store); err != nil {
		t.Fatalf("seed: %v", err)
	}
	if store.Count() != 3 {
		t.Fatalf("expected 3 demo users, got %d", store.Count())
	}

	bus := eventbus.New()
	assessment := agent.NewAssessmentAgent(bus)
	assessment.SetPersist(db)
	assessment.Start()

	learnerID := "learner-persist-1"
	bus.Publish(eventbus.Event{
		Type: eventbus.StudentSubmission, Source: "test", LearnerID: learnerID,
		Data: map[string]interface{}{"knowledge_id": "algebra", "is_correct": true},
	})

	db2, err := persist.Open(path)
	if err != nil {
		t.Fatalf("reopen: %v", err)
	}
	defer db2.Close()
	rows, err := db2.LoadStates(learnerID)
	if err != nil {
		t.Fatalf("load states: %v", err)
	}
	if len(rows) != 1 || rows[0].Attempts < 1 {
		t.Fatalf("expected persisted mastery, got %+v", rows)
	}

	store2 := auth.NewUserStore()
	if err := db2.LoadUsers(store2); err != nil {
		t.Fatalf("load users: %v", err)
	}
	if store2.Count() != 3 {
		t.Fatalf("reload users want 3 got %d", store2.Count())
	}
}

func TestBizEntitiesPersist(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "edu.db")
	db, err := persist.Open(path)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	defer db.Close()

	type q struct {
		ID   string `json:"id"`
		Stem string `json:"stem"`
	}
	if err := db.UpsertBiz("question", "q1", q{ID: "q1", Stem: "1+1?"}); err != nil {
		t.Fatalf("upsert: %v", err)
	}
	if err := db.UpsertRAGChunk(persist.RAGChunkRow{
		ID: "c1", DocID: "d1", Text: "hello", Vector: []float64{0.1, 0.2},
		Metadata: map[string]interface{}{"doc_id": "d1"},
	}); err != nil {
		t.Fatalf("rag upsert: %v", err)
	}

	db2, err := persist.Open(path)
	if err != nil {
		t.Fatalf("reopen: %v", err)
	}
	defer db2.Close()

	var found bool
	if err := db2.LoadBizKind("question", func(id string, data []byte) error {
		if id == "q1" {
			found = true
		}
		return nil
	}); err != nil {
		t.Fatalf("load biz: %v", err)
	}
	if !found {
		t.Fatal("question not loaded")
	}
	rows, err := db2.LoadRAGChunks()
	if err != nil || len(rows) != 1 || rows[0].Text != "hello" {
		t.Fatalf("rag reload: %+v err=%v", rows, err)
	}
}

func TestCritiquesPersist(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "edu.db")
	db, err := persist.Open(path)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	defer db.Close()

	id, err := db.InsertCritique(persist.CritiqueRow{
		LearnerID: "lrn1", KnowledgeID: "algebra", TeachingEventID: "evt-1",
		Overall: 2, Scores: map[string]float64{"pedagogical": 2},
		Critique: "too short", NeedsRegeneration: true,
		OriginalResponse: "ok", CriticModel: "heuristic", CriticTokens: 0,
	})
	if err != nil || id <= 0 {
		t.Fatalf("insert: id=%d err=%v", id, err)
	}
	if err := db.MarkCritiqueRegenerated("evt-1", "better response"); err != nil {
		t.Fatalf("mark: %v", err)
	}
	n, err := db.CountCritiques()
	if err != nil || n != 1 {
		t.Fatalf("count=%d err=%v", n, err)
	}
	var regen int
	var text string
	err = db.SQL.QueryRow(`SELECT regenerated, regenerated_response FROM critiques WHERE teaching_event_id=?`, "evt-1").
		Scan(&regen, &text)
	if err != nil || regen != 1 || text != "better response" {
		t.Fatalf("regen row: regen=%d text=%q err=%v", regen, text, err)
	}
}
