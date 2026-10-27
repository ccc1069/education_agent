package llm

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"strings"
)

// CriticService LLM-as-judge Critic 服务 -- 对齐 Java CriticService
//
// 评估教学回复 + 自反思再生成:
// - Evaluate(): 对 TutorAgent 的回复打分(4 维度 + overall + critique)
// - Regenerate(): 把 critique 作为反馈,重新生成回复
//
// LLM 不可用时返回 heuristic 评分(基于文本特征),不阻塞主流程。
type CriticService struct {
	llm *LlmService
}

// NewCriticService 创建 CriticService
func NewCriticService(llm *LlmService) *CriticService {
	return &CriticService{llm: llm}
}

// CritiqueResult 评估结果 -- 对齐 Python CritiqueResult
// needs_regeneration 默认: overall <= 3（与 llm/critic_service.py 一致）
type CritiqueResult struct {
	Scores            map[string]float64 // pedagogical/appropriateness/clarity/engagement
	Overall           float64
	Critique          string
	NeedsRegeneration bool // overall <= 3（字段缺省时）
	Model             string
	Tokens            int
}

// RegenerationResult 再生成结果 -- 对齐 Java CriticService.RegenerationResult
type RegenerationResult struct {
	Text     string
	Metadata map[string]interface{}
}

// Evaluate 评估教学回复。LLM 不可用时降级到启发式评分。
func (s *CriticService) Evaluate(knowledgeID, level string, mastery float64,
	isCorrect *bool, teachingResponse, learnerMessage string) *CritiqueResult {

	userPrompt := BuildCriticUserPrompt(learnerMessage, teachingResponse, level)

	resp := s.llm.ChatOrFallback(context.Background(),
		NewRequest(CriticSystemPrompt, userPrompt))

	if resp != nil && resp.Content != "" {
		result := parseCriticJson(resp.Content, resp.Model, resp.TotalTokens)
		if result != nil {
			return result
		}
	}

	// 降级:启发式评分
	log.Printf("[CriticService] LLM 不可用或解析失败,降级到启发式评分")
	return heuristicEvaluate(teachingResponse)
}

// Regenerate 根据 critique 重新生成教学回复。失败时降级到原回复。
func (s *CriticService) Regenerate(knowledgeID, level string, mastery float64,
	isCorrect *bool, originalResponse, critique, learnerMessage string) *RegenerationResult {

	systemPrompt := GetTutorPrompt(level)
	userPrompt := Sanitize("原回复:\n" + originalResponse + "\n\n评审意见:\n" + critique +
		"\n\n请根据评审意见重新生成一段教学回复,保持苏格拉底式引导风格。")

	newResponse := s.llm.ChatString(context.Background(), NewRequest(systemPrompt, userPrompt))

	if newResponse != "" {
		return &RegenerationResult{
			Text:     newResponse,
			Metadata: map[string]interface{}{"llm_used": true, "fallback": "none", "regenerated": true},
		}
	}

	// 降级:返回原回复
	return &RegenerationResult{
		Text:     originalResponse,
		Metadata: map[string]interface{}{"llm_used": false, "fallback": "original", "regenerated": false},
	}
}

// parseCriticJson 解析 Critic LLM 返回的 JSON（阈值对齐 Python）
func parseCriticJson(content, model string, tokens int) *CritiqueResult {
	jsonStr := extractJson(content)
	if jsonStr == "" {
		return nil
	}

	var raw map[string]interface{}
	if err := json.Unmarshal([]byte(jsonStr), &raw); err != nil {
		return nil
	}

	dimensions := []string{"pedagogical", "appropriateness", "clarity", "engagement"}
	scores := make(map[string]float64)
	if scoresRaw, ok := raw["scores"].(map[string]interface{}); ok {
		for _, dim := range dimensions {
			if v, ok := asFloat(scoresRaw[dim]); ok {
				scores[dim] = v
			} else {
				scores[dim] = 3.0
			}
		}
	} else {
		for _, dim := range dimensions {
			scores[dim] = 3.0
		}
	}

	overall, ok := asFloat(raw["overall"])
	if !ok || overall == 0 {
		sum := 0.0
		for _, v := range scores {
			sum += v
		}
		if len(scores) > 0 {
			overall = float64(int(sum) / len(scores)) // 对齐 Python 整数均值兜底
		} else {
			overall = 3
		}
	} else {
		overall = float64(int(overall)) // 对齐 Python int(overall_raw)
	}

	// Python: needs_reg = bool(data.get("needs_regeneration", overall <= 3))
	needsRegen := overall <= 3
	if v, exists := raw["needs_regeneration"]; exists {
		needsRegen = asBool(v)
	}

	critiqueText, _ := raw["critique"].(string)
	if critiqueText == "" {
		critiqueText = "无具体建议"
	}
	if len(critiqueText) > 500 {
		critiqueText = critiqueText[:500]
	}

	return &CritiqueResult{
		Scores:            scores,
		Overall:           overall,
		Critique:          critiqueText,
		NeedsRegeneration: needsRegen,
		Model:             model,
		Tokens:            tokens,
	}
}

func asFloat(v interface{}) (float64, bool) {
	switch n := v.(type) {
	case float64:
		return n, true
	case json.Number:
		f, err := n.Float64()
		return f, err == nil
	case int:
		return float64(n), true
	case int64:
		return float64(n), true
	case string:
		var f float64
		if _, err := fmt.Sscanf(n, "%f", &f); err == nil {
			return f, true
		}
	}
	return 0, false
}

func asBool(v interface{}) bool {
	switch b := v.(type) {
	case bool:
		return b
	case string:
		return b == "true" || b == "1"
	case float64:
		return b != 0
	default:
		return false
	}
}

// heuristicEvaluate 启发式评分(无 LLM 时的降级策略)
func heuristicEvaluate(response string) *CritiqueResult {
	if response == "" {
		return &CritiqueResult{
			Scores: map[string]float64{
				"pedagogical": 2, "appropriateness": 2, "clarity": 2, "engagement": 2},
			Overall:           2,
			Critique:          "回复为空",
			NeedsRegeneration: true,
			Model:             "heuristic",
		}
	}

	lenResp := len(response)
	hasQuestion := strings.Contains(response, "?") || strings.Contains(response, "？")
	hasEncouragement := strings.Contains(response, "好") || strings.Contains(response, "很好") ||
		strings.Contains(response, "不错") || strings.Contains(response, "加油")
	hasGuidance := strings.Contains(response, "试着") || strings.Contains(response, "想一想") ||
		strings.Contains(response, "思考") || strings.Contains(response, "引导")

	pedagogical := clampScore(3 + boolToInt(hasGuidance) + boolToInt(hasQuestion))
	appropriateness := clampScore(3 + boolToInt(hasEncouragement))
	clarity := 3
	if lenResp > 50 {
		clarity = 4
	}
	engagement := clampScore(3 + boolToInt(hasQuestion) + boolToInt(hasEncouragement))

	overall := float64((pedagogical + appropriateness + clarity + engagement) / 4)

	scores := map[string]float64{
		"pedagogical":     float64(pedagogical),
		"appropriateness": float64(appropriateness),
		"clarity":         float64(clarity),
		"engagement":      float64(engagement),
	}

	critiqueText := "回复质量良好,包含有效教学策略"
	if overall <= 3 {
		critiqueText = "回复可改进: 建议增加引导性提问和鼓励语"
	}

	return &CritiqueResult{
		Scores:            scores,
		Overall:           overall,
		Critique:          critiqueText,
		NeedsRegeneration: overall <= 3,
		Model:             "heuristic",
	}
}

// extractJson 从内容中提取 JSON 字符串
func extractJson(content string) string {
	jsonStr := content
	if idx := strings.Index(jsonStr, "```json"); idx >= 0 {
		jsonStr = jsonStr[idx+7:]
		if end := strings.Index(jsonStr, "```"); end >= 0 {
			jsonStr = jsonStr[:end]
		}
	} else if idx := strings.Index(jsonStr, "```"); idx >= 0 {
		jsonStr = jsonStr[idx+3:]
		if end := strings.Index(jsonStr, "```"); end >= 0 {
			jsonStr = jsonStr[:end]
		}
	}
	return strings.TrimSpace(jsonStr)
}

// clampScore 限制分数在 1-5
func clampScore(v int) int {
	if v < 1 {
		return 1
	}
	if v > 5 {
		return 5
	}
	return v
}

// boolToInt 布尔转整数
func boolToInt(b bool) int {
	if b {
		return 1
	}
	return 0
}
