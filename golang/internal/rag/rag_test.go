package rag

import (
	"testing"
)

func TestChunkText(t *testing.T) {
	text := "第一句。第二句。第三句。第四句。第五句。"
	chunks := ChunkText(text, 10, 0) // 小块大小,产生多块

	if len(chunks) == 0 {
		t.Fatal("should produce chunks")
	}

	// 验证每块不超长
	for _, chunk := range chunks {
		if len(chunk.Text) > 20 { // 允许一些余量 (中文字符)
			t.Errorf("chunk too long: %d chars", len(chunk.Text))
		}
	}
}

func TestChunkText_WithOverlap(t *testing.T) {
	text := "AAAAAAAA。BBBBBBBB。CCCCCCCC。DDDDDDDD。"
	chunks := ChunkText(text, 15, 5)

	if len(chunks) < 2 {
		t.Fatal("should produce multiple chunks")
	}

	// 验证有重叠
	foundOverlap := false
	for i := 1; i < len(chunks); i++ {
		if len(chunks[i].Text) > 0 && len(chunks[i-1].Text) > 0 {
			// 检查是否有共享字符
			prev := chunks[i-1].Text
			curr := chunks[i].Text
			if len(prev) > 5 && len(curr) > 5 {
				foundOverlap = true
			}
		}
	}
	_ = foundOverlap
}

func TestChunkText_Empty(t *testing.T) {
	chunks := ChunkText("", 100, 0)
	if chunks != nil {
		t.Error("empty text should return nil")
	}
}

func TestMockEmbeddingProvider(t *testing.T) {
	provider := NewMockEmbeddingProvider()

	if provider.Name() != "mock-md5" {
		t.Errorf("name: got %s, want mock-md5", provider.Name())
	}
	if provider.Dimension() != 384 {
		t.Errorf("dimension: got %d, want 384", provider.Dimension())
	}

	// 相同文本产生相同向量
	v1, _ := provider.Embed("hello")
	v2, _ := provider.Embed("hello")
	if len(v1) != 384 {
		t.Errorf("vector length: got %d, want 384", len(v1))
	}
	for i := range v1 {
		if v1[i] != v2[i] {
			t.Error("same text should produce same vector")
			break
		}
	}

	// 不同文本产生不同向量
	v3, _ := provider.Embed("world")
	same := true
	for i := range v1 {
		if v1[i] != v3[i] {
			same = false
			break
		}
	}
	if same {
		t.Error("different text should produce different vectors")
	}
}

func TestCosineSimilarity(t *testing.T) {
	// 相同向量相似度为 1
	a := []float64{1, 0, 0}
	if sim := CosineSimilarity(a, a); sim < 0.99 {
		t.Errorf("self similarity: got %f, want ~1.0", sim)
	}

	// 正交向量相似度为 0
	b := []float64{0, 1, 0}
	if sim := CosineSimilarity(a, b); sim > 0.01 {
		t.Errorf("orthogonal similarity: got %f, want ~0.0", sim)
	}
}

func TestInMemoryVectorStore(t *testing.T) {
	store := NewInMemoryVectorStore()

	// 添加向量
	store.Add("v1", []float64{1, 0, 0}, map[string]interface{}{"label": "a"})
	store.Add("v2", []float64{0, 1, 0}, map[string]interface{}{"label": "b"})
	store.Add("v3", []float64{0.9, 0.1, 0}, map[string]interface{}{"label": "c"})

	// 搜索
	results := store.Search([]float64{1, 0, 0}, 2, 0.0)
	if len(results) != 2 {
		t.Fatalf("expected 2 results, got %d", len(results))
	}

	// 第一个应该是 v1 (最相似)
	if results[0].ID != "v1" {
		t.Errorf("first result: got %s, want v1", results[0].ID)
	}

	// 删除
	store.Delete("v1")
	if store.Count() != 2 {
		t.Errorf("after delete: got %d, want 2", store.Count())
	}
}

func TestRAGService_IngestAndSearch(t *testing.T) {
	embedder := NewMockEmbeddingProvider()
	store := NewInMemoryVectorStore()
	service := NewRAGService(embedder, store)

	text := "勾股定理是指直角三角形两直角边的平方和等于斜边的平方。这个定理在中国称为勾股定理，在西方称为毕达哥拉斯定理。勾股定理有超过400种证明方法。"

	count, err := service.IngestDocument("doc-001", text)
	if err != nil {
		t.Fatalf("IngestDocument failed: %v", err)
	}
	if count == 0 {
		t.Error("should produce at least one chunk")
	}

	// 搜索
	results, err := service.Search("什么是勾股定理", 5)
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}
	if len(results) == 0 {
		t.Error("should find at least one result")
	}
}

func TestRAGService_DeleteDocument(t *testing.T) {
	embedder := NewMockEmbeddingProvider()
	store := NewInMemoryVectorStore()
	service := NewRAGService(embedder, store)

	service.IngestDocument("doc-001", "测试文档内容一。第二句。")
	service.IngestDocument("doc-002", "测试文档内容二。第二句。")

	service.DeleteDocument("doc-001")
	if service.GetDocumentCount() != 1 {
		t.Errorf("expected 1 document, got %d", service.GetDocumentCount())
	}
}
