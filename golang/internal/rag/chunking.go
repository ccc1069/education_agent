package rag

import (
	"fmt"
	"strings"
)

// Chunk 文本块
type Chunk struct {
	ID       string                 `json:"id"`
	Text     string                 `json:"text"`
	Index    int                    `json:"index"`
	Metadata map[string]interface{} `json:"metadata"`
}

// isSentenceEnd 判断是否为句末标点
func isSentenceEnd(r rune) bool {
	return r == '。' || r == '.' || r == '!' || r == '?' || r == '！' || r == '？'
}

// ChunkText 按句边界切块
//
// 策略:
// 1. 按句末标点切分句子
// 2. 贪心打包,每块不超过 maxChars
// 3. 相邻块之间有 overlap 个字符重叠
func ChunkText(text string, maxChars int, overlap int) []Chunk {
	if text == "" {
		return nil
	}
	if maxChars <= 0 {
		maxChars = 500
	}

	// 切分句子 (按句末标点)
	var sentences []string
	var current strings.Builder
	for _, r := range text {
		current.WriteRune(r)
		if isSentenceEnd(r) {
			s := strings.TrimSpace(current.String())
			if s != "" {
				sentences = append(sentences, s)
			}
			current.Reset()
		}
	}
	// 最后没有标点的部分
	if current.Len() > 0 {
		s := strings.TrimSpace(current.String())
		if s != "" {
			sentences = append(sentences, s)
		}
	}

	var chunks []Chunk
	var buf strings.Builder
	index := 0

	for _, sentence := range sentences {
		// 如果当前块加上新句子超限,先保存当前块
		if buf.Len() > 0 && buf.Len()+len(sentence) > maxChars {
			chunks = append(chunks, Chunk{
				ID:    generateChunkID(index),
				Text:  buf.String(),
				Index: index,
			})
			index++

			// 重叠: 从当前块末尾取 overlap 个字符
			prev := buf.String()
			if overlap > 0 && len(prev) > overlap {
				buf.Reset()
				buf.WriteString(prev[len(prev)-overlap:])
			} else {
				buf.Reset()
			}
		}

		if buf.Len() > 0 {
			buf.WriteString(" ")
		}
		buf.WriteString(sentence)
	}

	// 最后一块
	if buf.Len() > 0 {
		chunks = append(chunks, Chunk{
			ID:    generateChunkID(index),
			Text:  buf.String(),
			Index: index,
		})
	}

	return chunks
}

func generateChunkID(index int) string {
	return fmt.Sprintf("chunk-%d", index)
}
