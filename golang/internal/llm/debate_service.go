package llm

import (
	"context"
	"encoding/json"
	"log"
	"strconv"
	"strings"
)

// DebateService Multi-Agent Debate 服务 -- 对齐 Java DebateService
//
// 2-persona 辩论(socratic vs direct),N 轮互相批评+修订,Synthesizer 综合产出 consensus。
//
// LLM 不可用时降级到启发式综合。
type DebateService struct {
	llm    *LlmService
	rounds int
}

// NewDebateService 创建 DebateService
func NewDebateService(llm *LlmService, rounds int) *DebateService {
	if rounds < 1 {
		rounds = 2
	}
	if rounds > 4 {
		rounds = 4
	}
	return &DebateService{llm: llm, rounds: rounds}
}

// DebateResult 辩论结果 -- 对齐 Java DebateService.DebateResult
type DebateResult struct {
	Consensus      string
	SocraticFinal  string
	DirectFinal    string
	RoundsCompleted int
	Metadata       map[string]interface{}
}

// RunDebate 运行完整辩论流程。LLM 不可用时降级到启发式综合。
func (s *DebateService) RunDebate(knowledgeID, level string, mastery float64, question string) *DebateResult {
	topic := Sanitize(knowledgeID + ": " + question)

	// 尝试 LLM 辩论
	result, err := s.runLlmDebate(topic)
	if err == nil && result != nil && result.Consensus != "" {
		return result
	}

	log.Printf("[DebateService] LLM 不可用,降级到启发式辩论: %v", err)

	// 降级:启发式综合
	return heuristicDebate(knowledgeID, level, mastery, question)
}

// runLlmDebate 执行 LLM 辩论流程
func (s *DebateService) runLlmDebate(topic string) (*DebateResult, error) {
	// 第 1 轮:Socratic vs Direct 各陈词
	socraticArg, err := s.llmDebateTurn(DebateSocraticPrompt, topic, "")
	if err != nil {
		return nil, err
	}
	directArg, err := s.llmDebateTurn(DebateDirectPrompt, topic, "")
	if err != nil {
		return nil, err
	}

	// 中间轮:互相批评+修订
	for r := 1; r < s.rounds; r++ {
		socraticArg, err = s.llmDebateTurn(DebateSocraticPrompt, topic,
			"对方观点: "+directArg+"\n请基于对方观点进一步阐述。")
		if err != nil {
			return nil, err
		}
		directArg, err = s.llmDebateTurn(DebateDirectPrompt, topic,
			"对方观点: "+socraticArg+"\n请基于对方观点进一步阐述。")
		if err != nil {
			return nil, err
		}
	}

	// Synthesizer 综合
	synthesisUserPrompt := BuildDebateContextPrompt(topic, socraticArg, directArg)
	synthesisResp := s.llm.ChatOrFallback(context.Background(),
		NewRequest(SynthesizerPrompt, synthesisUserPrompt))

	consensus := ""
	if synthesisResp != nil {
		consensus = parseSynthesis(synthesisResp.Content, socraticArg, directArg)
	}

	if consensus == "" {
		// 综合失败时拼接双方观点
		consensus = "【综合】\n苏格拉底式: " + truncate(socraticArg, 150) +
			"\n\n直接论辩式: " + truncate(directArg, 150)
	}

	return &DebateResult{
		Consensus:       consensus,
		SocraticFinal:   socraticArg,
		DirectFinal:     directArg,
		RoundsCompleted: s.rounds,
		Metadata: map[string]interface{}{
			"llm_used":      true,
			"rounds":        s.rounds,
			"personas":      "socratic,direct",
			"orchestrator":  "sequential_loop",
		},
	}, nil
}

// llmDebateTurn 单轮辩论 LLM 调用,返回 argument 文本
func (s *DebateService) llmDebateTurn(systemPrompt, topic, ctx string) (string, error) {
	userPrompt := topic + "\n\n请陈述你的立场。\n```json"
	if ctx != "" {
		userPrompt = topic + "\n\n" + ctx + "\n\n```json"
	}

	resp := s.llm.ChatOrFallback(context.Background(),
		NewRequest(systemPrompt, Sanitize(userPrompt)))

	if resp == nil {
		return "", &LlmUnavailableError{Message: "LLM 不可用", Retryable: true}
	}

	return extractArgument(resp.Content), nil
}

// extractArgument 从 JSON 响应中提取 argument 字段
func extractArgument(content string) string {
	jsonStr := extractJson(content)
	if jsonStr == "" {
		return content
	}

	var root struct {
		Argument string `json:"argument"`
	}
	if err := json.Unmarshal([]byte(jsonStr), &root); err == nil && root.Argument != "" {
		return root.Argument
	}
	return content
}

// parseSynthesis 解析 Synthesizer JSON,提取 synthesis 字段
func parseSynthesis(content, socraticArg, directArg string) string {
	jsonStr := extractJson(content)
	if jsonStr == "" {
		return ""
	}

	var root struct {
		Consensus            string `json:"consensus"`
		Synthesis            string `json:"synthesis"`
		RemainingDisagreements string `json:"remaining_disagreements"`
	}
	if err := json.Unmarshal([]byte(jsonStr), &root); err != nil {
		return ""
	}

	if root.Synthesis != "" {
		return root.Synthesis
	}
	// fallback: consensus + synthesis
	parts := []string{}
	if root.Consensus != "" {
		parts = append(parts, root.Consensus)
	}
	if root.Synthesis != "" {
		parts = append(parts, root.Synthesis)
	}
	return strings.Join(parts, "\n\n")
}

// heuristicDebate 启发式辩论综合(无 LLM 时的降级策略)
func heuristicDebate(knowledgeID, level string, mastery float64, question string) *DebateResult {
	socratic := "关于「" + knowledgeID + "」,让我们一起来思考:" + question + "\n\n" +
		"首先,你认为这个问题的关键点是什么?试着说说你的理解。\n" +
		"如果卡住了,可以想想:这个知识点和之前学过的哪些内容有关?"

	direct := "关于「" + knowledgeID + "」的直接讲解:" + question + "\n\n" +
		"核心概念:这是" + level + "级别的重要知识点。当前掌握度: " +
		fmtPercent(mastery) + "。\n建议:通过例题巩固理解,然后尝试变式练习。"

	consensus := "【综合回复】关于「" + knowledgeID + "」:\n\n" +
		"启发式引导: " + truncate(socratic, 80) + "\n\n" +
		"直接讲解: " + truncate(direct, 80) + "\n\n" +
		"建议:先理解概念,再通过练习巩固。"

	return &DebateResult{
		Consensus:       consensus,
		SocraticFinal:   socratic,
		DirectFinal:     direct,
		RoundsCompleted: 2,
		Metadata: map[string]interface{}{
			"llm_used":     false,
			"rounds":       2,
			"personas":     "socratic,direct",
			"orchestrator": "heuristic_stub",
		},
	}
}

// fmtPercent 格式化百分比
func fmtPercent(f float64) string {
	return strconv.FormatFloat(f*100, 'f', 0, 64) + "%"
}

// truncate 截断字符串
func truncate(s string, maxLen int) string {
	// 按 rune 截断避免中文乱码
	runes := []rune(s)
	if len(runes) <= maxLen {
		return s
	}
	return string(runes[:maxLen]) + "..."
}

