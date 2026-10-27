package privacy

import (
	"bytes"
	"testing"
)

func TestEncryptPII_DecryptPII(t *testing.T) {
	key := GenerateKey()
	plaintext := "敏感个人信息: 13800138000"

	encrypted, err := EncryptPII(plaintext, key)
	if err != nil {
		t.Fatalf("EncryptPII failed: %v", err)
	}
	if encrypted == plaintext {
		t.Error("encrypted should not equal plaintext")
	}

	decrypted, err := DecryptPII(encrypted, key)
	if err != nil {
		t.Fatalf("DecryptPII failed: %v", err)
	}
	if decrypted != plaintext {
		t.Errorf("got %s, want %s", decrypted, plaintext)
	}
}

func TestEncryptPII_WrongKey(t *testing.T) {
	key1 := GenerateKey()
	key2 := GenerateKey()
	plaintext := "test data"

	encrypted, _ := EncryptPII(plaintext, key1)
	_, err := DecryptPII(encrypted, key2)
	if err == nil {
		t.Error("decrypt with wrong key should fail")
	}
}

func TestEncryptPII_DifferentIVs(t *testing.T) {
	key := GenerateKey()
	plaintext := "same text"

	enc1, _ := EncryptPII(plaintext, key)
	enc2, _ := EncryptPII(plaintext, key)

	if enc1 == enc2 {
		t.Error("same plaintext should produce different ciphertexts (random IV)")
	}
}

func TestEncryptPII_InvalidKeySize(t *testing.T) {
	_, err := EncryptPII("test", []byte("short"))
	if err == nil {
		t.Error("should fail with short key")
	}
}

func TestMaskEmail(t *testing.T) {
	tests := []struct {
		input string
		want  string
	}{
		{"alice@example.com", "a***@example.com"},
		{"ab@example.com", "a***@example.com"},
		{"a@b.com", "a@b.com"}, // too short
	}
	for _, tt := range tests {
		got := MaskEmail(tt.input)
		if got != tt.want {
			t.Errorf("MaskEmail(%q) = %q, want %q", tt.input, got, tt.want)
		}
	}
}

func TestMaskPhone(t *testing.T) {
	got := MaskPhone("13800138000")
	want := "138****8000"
	if got != want {
		t.Errorf("got %s, want %s", got, want)
	}
}

func TestMaskIDCard(t *testing.T) {
	got := MaskIDCard("110101199001011234")
	want := "110***********1234"
	if got != want {
		t.Errorf("got %s, want %s", got, want)
	}
}

func TestMaskName(t *testing.T) {
	tests := []struct {
		input string
		want  string
	}{
		{"张三", "张*"},
		{"李小四", "李**"},
		{"王", "王"},
	}
	for _, tt := range tests {
		got := MaskName(tt.input)
		if got != tt.want {
			t.Errorf("MaskName(%q) = %q, want %q", tt.input, got, tt.want)
		}
	}
}

func TestPrivacyService_RecordConsent(t *testing.T) {
	service := NewPrivacyService()

	// 同意 analytics
	service.RecordConsent("user-001", ConsentAnalytics, true, "127.0.0.1", "test")
	if !service.GetConsent("user-001", ConsentAnalytics) {
		t.Error("should have analytics consent")
	}

	// 撤回
	service.RecordConsent("user-001", ConsentAnalytics, false, "127.0.0.1", "test")
	if service.GetConsent("user-001", ConsentAnalytics) {
		t.Error("consent should be revoked")
	}
}

func TestPrivacyService_GetAllConsents(t *testing.T) {
	service := NewPrivacyService()

	service.RecordConsent("user-001", ConsentAnalytics, true, "127.0.0.1", "")
	service.RecordConsent("user-001", ConsentMarketing, false, "127.0.0.1", "")

	consents := service.GetAllConsents("user-001")
	if len(consents) != 2 {
		t.Errorf("expected 2 consent types, got %d", len(consents))
	}
	if !consents[ConsentAnalytics] {
		t.Error("analytics should be granted")
	}
	if consents[ConsentMarketing] {
		t.Error("marketing should be denied")
	}
}

func TestPrivacyService_ExportUserData(t *testing.T) {
	service := NewPrivacyService()

	job, err := service.ExportUserData("user-001")
	if err != nil {
		t.Fatalf("ExportUserData failed: %v", err)
	}
	if job.Status != "completed" {
		t.Errorf("status: got %s, want completed", job.Status)
	}

	jobs := service.GetExportJobs("user-001")
	if len(jobs) != 1 {
		t.Errorf("expected 1 export job, got %d", len(jobs))
	}
}

func TestPrivacyService_DeletionWorkflow(t *testing.T) {
	service := NewPrivacyService()

	// 1. 请求删除
	req, err := service.RequestDeletion("user-001", "no longer needed")
	if err != nil {
		t.Fatalf("RequestDeletion failed: %v", err)
	}
	if req.Status != "pending" {
		t.Errorf("status: got %s, want pending", req.Status)
	}

	// 2. 确认删除
	err = service.ConfirmDeletion("user-001", req.ID)
	if err != nil {
		t.Fatalf("ConfirmDeletion failed: %v", err)
	}

	// 3. 执行删除
	err = service.ExecuteDeletion("user-001")
	if err != nil {
		t.Fatalf("ExecuteDeletion failed: %v", err)
	}

	// 4. 验证数据已清除
	if len(service.consents) > 0 {
		t.Error("consents should be cleared")
	}
}

func TestPrivacyService_DeletionRequests(t *testing.T) {
	service := NewPrivacyService()

	service.RequestDeletion("user-001", "reason1")
	service.RequestDeletion("user-001", "reason2")

	requests := service.GetDeletionRequests("user-001")
	if len(requests) != 2 {
		t.Errorf("expected 2 deletion requests, got %d", len(requests))
	}
}

func TestGenerateKey(t *testing.T) {
	key1 := GenerateKey()
	key2 := GenerateKey()

	if len(key1) != 32 {
		t.Errorf("key length: got %d, want 32", len(key1))
	}
	if bytes.Equal(key1, key2) {
		t.Error("keys should be different")
	}
}
