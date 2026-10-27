package com.edu.agent.tenant;

import com.edu.agent.db.entity.Learner;
import com.edu.agent.db.repository.LearnerRepository;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigInteger;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 多租户隔离集成测试: 验证 @Filter("tenantFilter") 正确隔离不同 tenant_id 的数据。
 */
@SpringBootTest
@ActiveProfiles("test")
class TenantIsolationTest {

    @Autowired
    LearnerRepository learnerRepository;

    private static final BigInteger TENANT_A = BigInteger.valueOf(1001);
    private static final BigInteger TENANT_B = BigInteger.valueOf(1002);

    @BeforeEach
    @Transactional
    void seed() {
        // Tenant A: 2 learners
        learnerRepository.save(makeLearner(TENANT_A, "learner-a1"));
        learnerRepository.save(makeLearner(TENANT_A, "learner-a2"));
        // Tenant B: 3 learners
        learnerRepository.save(makeLearner(TENANT_B, "learner-b1"));
        learnerRepository.save(makeLearner(TENANT_B, "learner-b2"));
        learnerRepository.save(makeLearner(TENANT_B, "learner-b3"));
    }

    @AfterEach
    @Transactional
    void cleanup() {
        // 用 cross-tenant 模式清理所有数据
        TenantContext.clear();
        learnerRepository.deleteAll();
    }

    @Test
    @Transactional
    void tenantA_seesOnlyOwnLearners() {
        TenantContext.set(TENANT_A);
        List<Learner> rows = learnerRepository.findAll();
        assertThat(rows).hasSize(2);
        assertThat(rows).allMatch(l -> TENANT_A.equals(l.getTenantId()));
    }

    @Test
    @Transactional
    void tenantB_seesOnlyOwnLearners() {
        TenantContext.set(TENANT_B);
        List<Learner> rows = learnerRepository.findAll();
        assertThat(rows).hasSize(3);
        assertThat(rows).allMatch(l -> TENANT_B.equals(l.getTenantId()));
    }

    @Test
    @Transactional
    void noTenantContext_returnsAllRows() {
        // TenantContext 为 null 时,过滤器不启用 -> 返回全部
        TenantContext.clear();
        List<Learner> rows = learnerRepository.findAll();
        assertThat(rows.size()).isGreaterThanOrEqualTo(5);
    }

    @Test
    @Transactional
    void crossTenantQuery_returnsZero() {
        // Tenant A 查询,不会看到 Tenant B 的数据
        TenantContext.set(TENANT_A);
        List<Learner> rows = learnerRepository.findAll();
        long bCount = rows.stream()
                .filter(l -> TENANT_B.equals(l.getTenantId()))
                .count();
        assertThat(bCount).isZero();
    }

    private Learner makeLearner(BigInteger tenantId, String publicId) {
        Learner l = new Learner();
        l.setTenantId(tenantId);
        l.setPublicId(publicId);
        l.setName(publicId);
        return l;
    }
}
