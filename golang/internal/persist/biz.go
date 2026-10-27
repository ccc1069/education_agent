package persist

import (
	"encoding/json"
	"fmt"
)

// biz_entities：题库 / 班级 / 作业 / RAG 的 JSON 落盘。

func (db *DB) migrateBiz() error {
	_, err := db.SQL.Exec(`
CREATE TABLE IF NOT EXISTS biz_entities (
  kind TEXT NOT NULL,
  id TEXT NOT NULL,
  data_json TEXT NOT NULL,
  PRIMARY KEY (kind, id)
);
CREATE TABLE IF NOT EXISTS rag_chunks (
  id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL,
  text TEXT NOT NULL,
  vector_json TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_rag_chunks_doc ON rag_chunks(doc_id);
`)
	return err
}

// UpsertBiz 写入业务实体 JSON。
func (db *DB) UpsertBiz(kind, id string, v any) error {
	raw, err := json.Marshal(v)
	if err != nil {
		return err
	}
	_, err = db.SQL.Exec(`
INSERT INTO biz_entities (kind, id, data_json) VALUES (?, ?, ?)
ON CONFLICT(kind, id) DO UPDATE SET data_json=excluded.data_json`, kind, id, string(raw))
	return err
}

// DeleteBiz 删除业务实体。
func (db *DB) DeleteBiz(kind, id string) error {
	_, err := db.SQL.Exec(`DELETE FROM biz_entities WHERE kind=? AND id=?`, kind, id)
	return err
}

// LoadBizKind 加载某类全部实体，对每行调用 fn。
func (db *DB) LoadBizKind(kind string, fn func(id string, data []byte) error) error {
	rows, err := db.SQL.Query(`SELECT id, data_json FROM biz_entities WHERE kind=?`, kind)
	if err != nil {
		return err
	}
	defer rows.Close()
	for rows.Next() {
		var id, data string
		if err := rows.Scan(&id, &data); err != nil {
			return err
		}
		if err := fn(id, []byte(data)); err != nil {
			return err
		}
	}
	return rows.Err()
}

// RAGChunkRow RAG 分块落盘行。
type RAGChunkRow struct {
	ID       string
	DocID    string
	Text     string
	Vector   []float64
	Metadata map[string]interface{}
}

// UpsertRAGChunk 写入或更新分块。
func (db *DB) UpsertRAGChunk(row RAGChunkRow) error {
	vec, err := json.Marshal(row.Vector)
	if err != nil {
		return err
	}
	meta, _ := json.Marshal(row.Metadata)
	if meta == nil {
		meta = []byte("{}")
	}
	_, err = db.SQL.Exec(`
INSERT INTO rag_chunks (id, doc_id, text, vector_json, metadata_json) VALUES (?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
  doc_id=excluded.doc_id,
  text=excluded.text,
  vector_json=excluded.vector_json,
  metadata_json=excluded.metadata_json`,
		row.ID, row.DocID, row.Text, string(vec), string(meta))
	return err
}

// DeleteRAGDoc 删除文档下全部分块。
func (db *DB) DeleteRAGDoc(docID string) error {
	_, err := db.SQL.Exec(`DELETE FROM rag_chunks WHERE doc_id=?`, docID)
	return err
}

// LoadRAGChunks 加载全部分块。
func (db *DB) LoadRAGChunks() ([]RAGChunkRow, error) {
	rows, err := db.SQL.Query(`SELECT id, doc_id, text, vector_json, metadata_json FROM rag_chunks`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []RAGChunkRow
	for rows.Next() {
		var row RAGChunkRow
		var vecJSON, metaJSON string
		if err := rows.Scan(&row.ID, &row.DocID, &row.Text, &vecJSON, &metaJSON); err != nil {
			return nil, err
		}
		if err := json.Unmarshal([]byte(vecJSON), &row.Vector); err != nil {
			return nil, fmt.Errorf("parse vector %s: %w", row.ID, err)
		}
		_ = json.Unmarshal([]byte(metaJSON), &row.Metadata)
		if row.Metadata == nil {
			row.Metadata = map[string]interface{}{}
		}
		out = append(out, row)
	}
	return out, rows.Err()
}
