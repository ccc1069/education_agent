package audit

import (
	"testing"
)

func TestAuditService_LogAction(t *testing.T) {
	service := NewAuditService([]byte("test-secret"))

	log := service.LogAction("tenant-001", "user-001", "login", "system", "127.0.0.1", "test-agent", nil)
	if log.ID == "" {
		t.Error("log ID should not be empty")
	}
	if log.TenantID != "tenant-001" {
		t.Errorf("TenantID: got %s, want tenant-001", log.TenantID)
	}
	if log.CurrHash == "" {
		t.Error("CurrHash should not be empty")
	}
	if log.PrevHash != "" {
		t.Error("first log should have empty PrevHash")
	}
}

func TestAuditService_ChainHash(t *testing.T) {
	service := NewAuditService([]byte("test-secret"))

	// 记录 3 条日志
	log1 := service.LogAction("tenant-001", "user-001", "login", "system", "127.0.0.1", "", nil)
	log2 := service.LogAction("tenant-001", "user-001", "view", "resource-1", "127.0.0.1", "", nil)
	log3 := service.LogAction("tenant-001", "user-001", "edit", "resource-1", "127.0.0.1", "", nil)

	// 验证链式哈希
	if log2.PrevHash != log1.CurrHash {
		t.Errorf("log2.PrevHash should equal log1.CurrHash")
	}
	if log3.PrevHash != log2.CurrHash {
		t.Errorf("log3.PrevHash should equal log2.CurrHash")
	}
	// 哈希应不同
	if log1.CurrHash == log2.CurrHash {
		t.Error("different logs should have different hashes")
	}
}

func TestAuditService_VerifyChain_Valid(t *testing.T) {
	service := NewAuditService([]byte("test-secret"))

	for i := 0; i < 10; i++ {
		service.LogAction("tenant-001", "user-001", "action", "target", "127.0.0.1", "", nil)
	}

	valid, brokenAt := service.VerifyChain()
	if !valid {
		t.Errorf("chain should be valid, broken at: %s", brokenAt)
	}
}

func TestAuditService_VerifyChain_Tampered(t *testing.T) {
	service := NewAuditService([]byte("test-secret"))

	service.LogAction("tenant-001", "user-001", "login", "system", "127.0.0.1", "", nil)
	service.LogAction("tenant-001", "user-001", "view", "resource-1", "127.0.0.1", "", nil)

	// 篡改第二条日志
	service.mu.Lock()
	service.logs[1].Action = "deleted"
	service.mu.Unlock()

	valid, brokenAt := service.VerifyChain()
	if valid {
		t.Error("chain should be invalid after tampering")
	}
	if brokenAt != service.logs[1].ID {
		t.Errorf("brokenAt should be log[1].ID, got %s", brokenAt)
	}
}

func TestAuditService_GetLogs(t *testing.T) {
	service := NewAuditService([]byte("test-secret"))

	service.LogAction("tenant-001", "user-001", "login", "system", "127.0.0.1", "", nil)
	service.LogAction("tenant-002", "user-002", "login", "system", "127.0.0.1", "", nil)
	service.LogAction("tenant-001", "user-001", "view", "resource-1", "127.0.0.1", "", nil)

	logs := service.GetLogs("tenant-001", 0)
	if len(logs) != 2 {
		t.Errorf("expected 2 logs for tenant-001, got %d", len(logs))
	}

	// 验证正序
	if logs[0].Action != "login" || logs[1].Action != "view" {
		t.Error("logs should be in chronological order")
	}
}

func TestAuditService_GetLogs_WithLimit(t *testing.T) {
	service := NewAuditService([]byte("test-secret"))

	for i := 0; i < 10; i++ {
		service.LogAction("tenant-001", "user-001", "action", "target", "127.0.0.1", "", nil)
	}

	logs := service.GetLogs("tenant-001", 5)
	if len(logs) != 5 {
		t.Errorf("expected 5 logs, got %d", len(logs))
	}
}

func TestAuditService_GetAllLogs(t *testing.T) {
	service := NewAuditService([]byte("test-secret"))

	service.LogAction("tenant-001", "user-001", "login", "system", "127.0.0.1", "", nil)
	service.LogAction("tenant-002", "user-002", "login", "system", "127.0.0.1", "", nil)

	logs := service.GetAllLogs(0)
	if len(logs) != 2 {
		t.Errorf("expected 2 logs, got %d", len(logs))
	}
}

func TestAuditService_Metadata(t *testing.T) {
	service := NewAuditService([]byte("test-secret"))

	metadata := map[string]interface{}{
		"field1": "value1",
		"count":  42,
	}
	log := service.LogAction("tenant-001", "user-001", "update", "resource-1", "127.0.0.1", "", metadata)
	if log.Metadata["field1"] != "value1" {
		t.Error("metadata should be preserved")
	}

	// 验证包含 metadata 的链
	valid, _ := service.VerifyChain()
	if !valid {
		t.Error("chain with metadata should be valid")
	}
}
