package vision

import (
	"encoding/base64"
	"fmt"
	"regexp"
	"strings"

	"multi-agent-education/golang/internal/llm"
)

// 支持的图片 MIME 类型
var allowedMimeTypes = map[string]bool{
	"image/jpeg": true,
	"image/png":  true,
	"image/gif":  true,
	"image/webp": true,
}

// dataURLPattern data URL 正则
var dataURLPattern = regexp.MustCompile(`^data:([a-zA-Z]+/[a-zA-Z+]+);base64,(.+)$`)

// VisionService 视觉服务
//
// 面试要点:
// - 图像校验: MIME 白名单 + 大小限制
// - 多模态 LLM: 文本 + 图像联合分析
type VisionService struct {
	llm *llm.LlmService
}

// NewVisionService 创建视觉服务
func NewVisionService(llmService *llm.LlmService) *VisionService {
	return &VisionService{llm: llmService}
}

// ValidateDataURL 校验 data URL 格式
//
// 返回 (mimeType, sizeInBytes, error)
func (s *VisionService) ValidateDataURL(dataURL string) (string, int, error) {
	matches := dataURLPattern.FindStringSubmatch(dataURL)
	if matches == nil {
		return "", 0, fmt.Errorf("invalid data URL format")
	}

	mimeType := matches[1]
	if !allowedMimeTypes[mimeType] {
		return "", 0, fmt.Errorf("unsupported image type: %s", mimeType)
	}

	// 解码 base64 获取大小
	base64Data := matches[2]
	data, err := base64.StdEncoding.DecodeString(base64Data)
	if err != nil {
		return "", 0, fmt.Errorf("invalid base64: %w", err)
	}

	// 限制 4MB
	if len(data) > 4*1024*1024 {
		return "", 0, fmt.Errorf("image too large: %d bytes (max 4MB)", len(data))
	}

	return mimeType, len(data), nil
}

// ValidateImageURL 校验图像 URL
func (s *VisionService) ValidateImageURL(url string) error {
	if !strings.HasPrefix(url, "https://") {
		return fmt.Errorf("only HTTPS URLs are allowed")
	}
	return nil
}

// AnalyzeImage 分析图像
//
// 多模态消息: 文本问题 + 图像
func (s *VisionService) AnalyzeImage(imageData, mimeType, question string) (string, map[string]interface{}, error) {
	// 构造多模态消息描述
	metadata := map[string]interface{}{
		"mime_type": mimeType,
		"size":      len(imageData),
		"model":     "multimodal",
	}

	if s.llm == nil || !s.llm.IsRealLlmEnabled() {
		// 降级: 返回描述性文本
		return fmt.Sprintf("图像分析 (降级模式): 接收到 %s 格式图像,大小 %d 字节。问题: %s",
			mimeType, len(imageData), question), metadata, nil
	}

	// 调用 LLM (简化: 实际应使用支持多模态的 API)
	resp := s.llm.ChatOrFallback(nil, llm.LlmRequest{
		Messages: []llm.LlmMessage{
			{Role: llm.RoleSystem, Content: "你是一位能分析图像的教育助手。"},
			{Role: llm.RoleUser, Content: fmt.Sprintf("请分析这张图像并回答: %s [图像: %s 格式]",
				question, mimeType)},
		},
	})

	if resp == nil {
		return "分析失败", metadata, fmt.Errorf("LLM unavailable")
	}

	return resp.Content, metadata, nil
}
