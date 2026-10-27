package rag

import (
	"crypto/md5"
	"encoding/binary"
	"math"
)

// EmbeddingProvider 嵌入向量提供者接口
type EmbeddingProvider interface {
	Name() string
	Dimension() int
	Embed(text string) ([]float64, error)
	EmbedBatch(texts []string) ([][]float64, error)
}

// MockEmbeddingProvider Mock 嵌入提供者
//
// 使用 MD5 哈希生成确定性 384 维向量, L2 归一化
// 相同文本总是产生相同向量 (适合测试和演示)
type MockEmbeddingProvider struct {
	dimension int
}

// NewMockEmbeddingProvider 创建 Mock 嵌入提供者
func NewMockEmbeddingProvider() *MockEmbeddingProvider {
	return &MockEmbeddingProvider{dimension: 384}
}

func (p *MockEmbeddingProvider) Name() string {
	return "mock-md5"
}

func (p *MockEmbeddingProvider) Dimension() int {
	return p.dimension
}

func (p *MockEmbeddingProvider) Embed(text string) ([]float64, error) {
	return p.hashToVector(text), nil
}

func (p *MockEmbeddingProvider) EmbedBatch(texts []string) ([][]float64, error) {
	vectors := make([][]float64, len(texts))
	for i, text := range texts {
		vectors[i] = p.hashToVector(text)
	}
	return vectors, nil
}

// hashToVector 将文本哈希为固定维度向量
func (p *MockEmbeddingProvider) hashToVector(text string) []float64 {
	// 使用 MD5 生成 16 字节哈希,重复填充到目标维度
	hash := md5.Sum([]byte(text))
	vector := make([]float64, p.dimension)

	for i := 0; i < p.dimension; i++ {
		// 每 2 字节生成一个 float64
		hashByte := hash[i%16]
		nextByte := hash[(i+1)%16]
		val := float64(int(hashByte)<<8|int(nextByte)) / 65535.0 // 归一化到 [0,1]
		vector[i] = val*2 - 1                                  // 映射到 [-1,1]
	}

	// L2 归一化
	norm := 0.0
	for _, v := range vector {
		norm += v * v
	}
	norm = math.Sqrt(norm)
	if norm > 0 {
		for i := range vector {
			vector[i] /= norm
		}
	}

	return vector
}

// CosineSimilarity 计算余弦相似度 (导出函数,供外部使用)
func CosineSimilarity(a, b []float64) float64 {
	if len(a) != len(b) {
		return 0
	}
	dot := 0.0
	normA := 0.0
	normB := 0.0
	for i := range a {
		dot += a[i] * b[i]
		normA += a[i] * a[i]
		normB += b[i] * b[i]
	}
	if normA == 0 || normB == 0 {
		return 0
	}
	return dot / (math.Sqrt(normA) * math.Sqrt(normB))
}

// 避免 unused import
var _ = binary.BigEndian
