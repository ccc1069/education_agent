package rag

import (
	"sync"
)

// SearchResult 向量搜索结果
type SearchResult struct {
	ID       string                 `json:"id"`
	Score    float64                `json:"score"`
	Metadata map[string]interface{} `json:"metadata"`
}

// VectorStore 向量存储接口
type VectorStore interface {
	Add(id string, vector []float64, metadata map[string]interface{}) error
	Search(query []float64, topK int, minScore float64) []SearchResult
	Delete(id string) error
}

// InMemoryVectorStore 内存向量存储
//
// 面试要点:
// - 使用 sync.RWMutex 支持并发读写
// - 暴力搜索 + 余弦相似度 (适合小规模数据)
// - 生产环境应使用 FAISS/Annoy 等 ANN 库
type InMemoryVectorStore struct {
	mu       sync.RWMutex
	vectors  map[string][]float64
	metadata map[string]map[string]interface{}
}

// NewInMemoryVectorStore 创建内存向量存储
func NewInMemoryVectorStore() *InMemoryVectorStore {
	return &InMemoryVectorStore{
		vectors:  make(map[string][]float64),
		metadata: make(map[string]map[string]interface{}),
	}
}

// Add 添加向量
func (s *InMemoryVectorStore) Add(id string, vector []float64, metadata map[string]interface{}) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	// 复制向量,避免外部修改
	v := make([]float64, len(vector))
	copy(v, vector)
	s.vectors[id] = v
	s.metadata[id] = metadata
	return nil
}

// Search 搜索最相似的向量
func (s *InMemoryVectorStore) Search(query []float64, topK int, minScore float64) []SearchResult {
	s.mu.RLock()
	defer s.mu.RUnlock()

	type scored struct {
		id    string
		score float64
	}

	var results []scored
	for id, vec := range s.vectors {
		sim := CosineSimilarity(query, vec)
		if sim >= minScore {
			results = append(results, scored{id, sim})
		}
	}

	// 按分数降序排序 (简单选择 topK)
	for i := 0; i < len(results) && i < topK; i++ {
		maxIdx := i
		for j := i + 1; j < len(results); j++ {
			if results[j].score > results[maxIdx].score {
				maxIdx = j
			}
		}
		results[i], results[maxIdx] = results[maxIdx], results[i]
	}

	// 截取 topK
	if len(results) > topK {
		results = results[:topK]
	}

	// 构造返回
	searchResults := make([]SearchResult, 0, len(results))
	for _, r := range results {
		meta := s.metadata[r.id]
		if meta == nil {
			meta = make(map[string]interface{})
		}
		searchResults = append(searchResults, SearchResult{
			ID:       r.id,
			Score:    r.score,
			Metadata: meta,
		})
	}
	return searchResults
}

// Delete 删除向量
func (s *InMemoryVectorStore) Delete(id string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	delete(s.vectors, id)
	delete(s.metadata, id)
	return nil
}

// Count 获取向量数量
func (s *InMemoryVectorStore) Count() int {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return len(s.vectors)
}

// Snapshot 导出全部向量（供落盘）
func (s *InMemoryVectorStore) Snapshot() (map[string][]float64, map[string]map[string]interface{}) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	vecs := make(map[string][]float64, len(s.vectors))
	metas := make(map[string]map[string]interface{}, len(s.metadata))
	for id, v := range s.vectors {
		cp := make([]float64, len(v))
		copy(cp, v)
		vecs[id] = cp
	}
	for id, m := range s.metadata {
		metas[id] = m
	}
	return vecs, metas
}
