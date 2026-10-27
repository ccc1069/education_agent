package com.edu.agent.audit;

import com.edu.agent.db.entity.AuditLog;
import com.edu.agent.db.repository.AuditLogRepository;
import com.edu.agent.service.AuditService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import java.math.BigInteger;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * HMAC 链完整性验证测试。
 */
@SpringBootTest
@ActiveProfiles("test")
class AuditChainTest {

    @Autowired
    AuditService auditService;

    @Autowired
    AuditLogRepository auditLogRepository;

    @BeforeEach
    void clean() {
        auditLogRepository.deleteAll();
    }

    @Test
    void writeThreeLogs_chainValidates() {
        BigInteger tenantId = BigInteger.ONE;
        auditService.logAction(tenantId, "alice@x.com", "class.create", "class:1", "1.2.3.4", "ua", Map.of("n", 1));
        auditService.logAction(tenantId, "bob@x.com", "assignment.create", "assignment:1", "1.2.3.4", "ua", Map.of());
        auditService.logAction(tenantId, "alice@x.com", "assignment.publish", "assignment:1", "1.2.3.4", "ua", Map.of());

        List<AuditLog> logs = auditLogRepository.findAll();
        assertThat(logs).hasSize(3);

        // 链: 第二条的 prev_hash == 第一条的 curr_hash
        AuditLog first = logs.stream().sorted(java.util.Comparator.comparing(AuditLog::getId)).toList().get(0);
        AuditLog second = logs.stream().sorted(java.util.Comparator.comparing(AuditLog::getId)).toList().get(1);
        AuditLog third = logs.stream().sorted(java.util.Comparator.comparing(AuditLog::getId)).toList().get(2);

        assertThat(second.getPrevHash()).isEqualTo(first.getCurrHash());
        assertThat(third.getPrevHash()).isEqualTo(second.getCurrHash());
        assertThat(first.getPrevHash()).isEmpty();

        // verify: 全部通过
        Map<String, Object> result = auditService.verifyChain(BigInteger.ONE);
        assertThat(result.get("valid")).isEqualTo(true);
        assertThat(result.get("checked")).isEqualTo(3);
        assertThat(result.get("broken_at")).isNull();
    }

    @Test
    void tamperOneLog_chainBreaks() {
        BigInteger tenantId = BigInteger.ONE;
        auditService.logAction(tenantId, "alice@x.com", "action.a", "t:1", "ip", "ua", Map.of());
        auditService.logAction(tenantId, "bob@x.com", "action.b", "t:2", "ip", "ua", Map.of());

        // 篡改第一条
        AuditLog first = auditLogRepository.findAll().stream()
                .min(java.util.Comparator.comparing(AuditLog::getId))
                .orElseThrow();
        first.setActor("hacker@x.com");
        auditLogRepository.save(first);

        Map<String, Object> result = auditService.verifyChain(BigInteger.ONE);
        assertThat(result.get("valid")).isEqualTo(false);
        assertThat(result.get("broken_at")).isNotNull();
    }
}
