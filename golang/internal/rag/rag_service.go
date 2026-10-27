package rag

import (
	"fmt"
	"sync"
)

// RAGService RAG 检索增强服务
//
// 面试要点:
// - 文档摄取: 切块 → 嵌入 → 存储
// - 语义检索: 查询嵌入 → 向量搜索 → 返回相关块
type RAGService struct {
	embedder   EmbeddingProvider
	store      VectorStore
	mu         sync.RWMutex
	chunks     map[string]Chunk
	docIndex   map[string][]string // docID -> chunkIDs
	onPersist  func(docID string, chunkIDs []string, chunks map[string]Chunk, store *InMemoryVectorStore) error
	onDelete   func(docID string) error
}

// NewRAGService 创建 RAG 服务
func NewRAGService(embedder EmbeddingProvider, store VectorStore) *RAGService {
	return &RAGService{
		embedder: embedder,
		store:    store,
		chunks:   make(map[string]Chunk),
		docIndex: make(map[string][]string),
	}
}

// SetPersistHooks 设置落盘钩子（仅 InMemoryVectorStore 可完整导出向量）
func (s *RAGService) SetPersistHooks(
	onPersist func(docID string, chunkIDs []string, chunks map[string]Chunk, store *InMemoryVectorStore) error,
	onDelete func(docID string) error,
) {
	s.onPersist = onPersist
	s.onDelete = onDelete
}

// RestoreChunk 启动时从磁盘恢复一块（不触发落盘）
func (s *RAGService) RestoreChunk(chunkID, docID, text string, vector []float64, metadata map[string]interface{}) error {
	if err := s.store.Add(chunkID, vector, metadata); err != nil {
		return err
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.chunks[chunkID] = Chunk{Text: text, Metadata: metadata}
	s.docIndex[docID] = append(s.docIndex[docID], chunkID)
	return nil
}

// IngestDocument 摄取文档
//
// 1. 文本切块
// 2. 生成嵌入向量
// 3. 存入向量存储
func (s *RAGService) IngestDocument(docID, text string) (int, error) {
	// 切块
	chunks := ChunkText(text, 500, 50)
	if len(chunks) == 0 {
		return 0, fmt.Errorf("no chunks generated")
	}

	// 嵌入并存储
	chunkIDs := make([]string, 0, len(chunks))
	for i, chunk := range chunks {
		chunk.Metadata = map[string]interface{}{
			"doc_id": docID,
			"index":  i,
		}

		vector, err := s.embedder.Embed(chunk.Text)
		if err != nil {
			return 0, fmt.Errorf("embed chunk %d: %w", i, err)
		}

		chunkID := fmt.Sprintf("%s-chunk-%d", docID, i)
		if err := s.store.Add(chunkID, vector, chunk.Metadata); err != nil {
			return 0, fmt.Errorf("store chunk %d: %w", i, err)
		}

		s.chunks[chunkID] = chunk
		chunkIDs = append(chunkIDs, chunkID)
	}

	s.mu.Lock()
	s.docIndex[docID] = chunkIDs
	s.mu.Unlock()

	if s.onPersist != nil {
		if mem, ok := s.store.(*InMemoryVectorStore); ok {
			_ = s.onPersist(docID, chunkIDs, s.chunks, mem)
		}
	}

	return len(chunks), nil
}

// Search 语义检索
//
// 1. 查询文本嵌入
// 2. 向量搜索 topK
// 3. 返回结果
func (s *RAGService) Search(query string, topK int) ([]SearchResult, error) {
	if topK <= 0 {
		topK = 5
	}

	queryVector, err := s.embedder.Embed(query)
	if err != nil {
		return nil, fmt.Errorf("embed query: %w", err)
	}

	return s.store.Search(queryVector, topK, 0.0), nil
}

// DeleteDocument 删除文档
func (s *RAGService) DeleteDocument(docID string) error {
	s.mu.Lock()
	chunkIDs := s.docIndex[docID]
	delete(s.docIndex, docID)
	s.mu.Unlock()

	for _, id := range chunkIDs {
		s.store.Delete(id)
		delete(s.chunks, id)
	}
	if s.onDelete != nil {
		_ = s.onDelete(docID)
	}
	return nil
}

// GetDocumentCount 获取文档数量
func (s *RAGService) GetDocumentCount() int {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return len(s.docIndex)
}

// GetChunkCount 获取总块数
func (s *RAGService) GetChunkCount() int {
	if store, ok := s.store.(*InMemoryVectorStore); ok {
		return store.Count()
	}
	return 0
}

// DocumentInfo 文档信息
type DocumentInfo struct {
	DocID      string `json:"doc_id"`
	ChunkCount int    `json:"chunk_count"`
}

// ListDocuments 列出所有文档
func (s *RAGService) ListDocuments() []DocumentInfo {
	s.mu.RLock()
	defer s.mu.RUnlock()

	result := make([]DocumentInfo, 0, len(s.docIndex))
	for docID, chunks := range s.docIndex {
		result = append(result, DocumentInfo{
			DocID:      docID,
			ChunkCount: len(chunks),
		})
	}
	return result
}

// GetDocument 获取文档详情 (含 chunks)
func (s *RAGService) GetDocument(docID string) (DocumentInfo, []Chunk, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	chunkIDs, ok := s.docIndex[docID]
	if !ok {
		return DocumentInfo{}, nil, false
	}
	chunks := make([]Chunk, 0, len(chunkIDs))
	for _, id := range chunkIDs {
		if c, ok := s.chunks[id]; ok {
			chunks = append(chunks, c)
		}
	}
	return DocumentInfo{DocID: docID, ChunkCount: len(chunkIDs)}, chunks, true
}
