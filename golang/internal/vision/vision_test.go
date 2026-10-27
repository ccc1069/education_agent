package vision

import (
	"encoding/base64"
	"strings"
	"testing"
)

func TestValidateDataURL_Valid(t *testing.T) {
	service := NewVisionService(nil)

	// 构造有效的 data URL
	header := []byte{0xFF, 0xD8, 0xFF, 0xE0} // JPEG header
	base64Data := base64.StdEncoding.EncodeToString(header)
	dataURL := "data:image/jpeg;base64," + base64Data

	mimeType, size, err := service.ValidateDataURL(dataURL)
	if err != nil {
		t.Fatalf("ValidateDataURL failed: %v", err)
	}
	if mimeType != "image/jpeg" {
		t.Errorf("mimeType: got %s, want image/jpeg", mimeType)
	}
	if size != len(header) {
		t.Errorf("size: got %d, want %d", size, len(header))
	}
}

func TestValidateDataURL_InvalidFormat(t *testing.T) {
	service := NewVisionService(nil)

	_, _, err := service.ValidateDataURL("not-a-data-url")
	if err == nil {
		t.Error("should fail with invalid format")
	}
}

func TestValidateDataURL_UnsupportedType(t *testing.T) {
	service := NewVisionService(nil)

	dataURL := "data:image/bmp;base64,AAAA"
	_, _, err := service.ValidateDataURL(dataURL)
	if err == nil {
		t.Error("should fail with unsupported type")
	}
}

func TestValidateDataURL_TooLarge(t *testing.T) {
	service := NewVisionService(nil)

	// 构造超过 4MB 的数据
	largeData := make([]byte, 5*1024*1024)
	base64Data := base64.StdEncoding.EncodeToString(largeData)
	dataURL := "data:image/png;base64," + base64Data

	_, _, err := service.ValidateDataURL(dataURL)
	if err == nil {
		t.Error("should fail with too large image")
	}
}

func TestValidateImageURL(t *testing.T) {
	service := NewVisionService(nil)

	// 有效
	err := service.ValidateImageURL("https://example.com/image.png")
	if err != nil {
		t.Errorf("HTTPS URL should be valid: %v", err)
	}

	// 无效
	err = service.ValidateImageURL("http://example.com/image.png")
	if err == nil {
		t.Error("HTTP URL should be invalid")
	}
}

func TestAnalyzeImage_Fallback(t *testing.T) {
	service := NewVisionService(nil)

	imageData := []byte{0xFF, 0xD8, 0xFF, 0xE0}
	result, metadata, err := service.AnalyzeImage(string(imageData), "image/jpeg", "这是什么?")
	if err != nil {
		t.Fatalf("AnalyzeImage failed: %v", err)
	}
	if !strings.Contains(result, "降级模式") {
		t.Errorf("should return fallback analysis, got: %s", result)
	}
	if metadata["mime_type"] != "image/jpeg" {
		t.Errorf("metadata mime_type: got %v, want image/jpeg", metadata["mime_type"])
	}
}
