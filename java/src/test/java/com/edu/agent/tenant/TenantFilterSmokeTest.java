package com.edu.agent.tenant;

import com.edu.agent.db.entity.Learner;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.hibernate.Session;
import org.hibernate.Filter;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import com.edu.agent.db.repository.LearnerRepository;

import java.math.BigInteger;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 验证 @Filter("tenantFilter") 在 EntityManager 直接调用时生效。
 * 这绕过了 Spring Data JPA 代理,直接验证 Hibernate filter 行为。
 */
@SpringBootTest
@ActiveProfiles("test")
class TenantFilterSmokeTest {

    @PersistenceContext
    EntityManager em;

    @Autowired
    LearnerRepository learnerRepository;

    private static final BigInteger TENANT_A = BigInteger.valueOf(1001);
    private static final BigInteger TENANT_B = BigInteger.valueOf(1002);

    @BeforeEach
    @Transactional
    void seed() {
        learnerRepository.deleteAll();
        learnerRepository.save(makeLearner(TENANT_A, "smoke-a1"));
        learnerRepository.save(makeLearner(TENANT_B, "smoke-b1"));
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
    void manualFilterEnabled_returnsOnlyTenantA() {
        // 启用 filter,只看 TENANT_A
        Session session = em.unwrap(Session.class);
        Filter filter = session.enableFilter("tenantFilter");
        filter.setParameter("tenantId", TENANT_A);

        List<Learner> rows = em.createQuery("SELECT l FROM Learner l", Learner.class).getResultList();
        assertThat(rows).hasSize(1);
        assertThat(rows.get(0).getPublicId()).isEqualTo("smoke-a1");
    }

    @Test
    @Transactional
    void manualFilterEnabled_tenantB_returnsOnlyTenantB() {
        Session session = em.unwrap(Session.class);
        Filter filter = session.enableFilter("tenantFilter");
        filter.setParameter("tenantId", TENANT_B);

        List<Learner> rows = em.createQuery("SELECT l FROM Learner l", Learner.class).getResultList();
        assertThat(rows).hasSize(1);
        assertThat(rows.get(0).getPublicId()).isEqualTo("smoke-b1");
    }

    private Learner makeLearner(BigInteger tenantId, String publicId) {
        Learner l = new Learner();
        l.setTenantId(tenantId);
        l.setPublicId(publicId);
        l.setName(publicId);
        return l;
    }
}
