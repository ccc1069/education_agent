package com.edu.agent.tenant;

import jakarta.persistence.EntityManager;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.hibernate.Session;
import org.hibernate.Filter;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.math.BigInteger;

/**
 * 切面: 在 Repository 调用前启用 tenant_filter。
 *
 * 关键: 使用 @Around 而非 @Before,确保在 Repository 方法体内(事务已开启时)
 * 读取 Session 并启用 filter。@Before 在事务开启前执行,拿到的 Session
 * 与 Repository 实际使用的 Session 不同。
 *
 * 通过 @Order 让本切面优先级低于 @Transactional 顾问(默认 Ordered.LOWEST_PRECEDENCE),
 * 这样 @Around 的 pjp.proceed() 会进入事务包裹后的 Repository 方法体。
 */
@Slf4j
@Aspect
@Component
@Order(Ordered.LOWEST_PRECEDENCE)
public class TenantFilterAspect {

    private final EntityManager entityManager;

    public TenantFilterAspect(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Around("execution(* com.edu.agent.db.repository.*.*(..)) || " +
            "execution(* org.springframework.data.jpa.repository.support.SimpleJpaRepository+.*(..))")
    public Object withTenantFilter(ProceedingJoinPoint pjp) throws Throwable {
        BigInteger tid = TenantContext.get();
        if (tid == null) {
            return pjp.proceed();
        }

        boolean txActive = TransactionSynchronizationManager.isActualTransactionActive();
        log.debug("tenant_filter_check: tenant={} method={} txActive={}", tid, pjp.getSignature().getName(), txActive);

        try {
            Session session = entityManager.unwrap(Session.class);
            Filter existing = session.getEnabledFilter(TenantFilterHelper.FILTER_NAME);
            if (existing == null) {
                Filter filter = session.enableFilter(TenantFilterHelper.FILTER_NAME);
                filter.setParameter(TenantFilterHelper.FILTER_PARAM, tid);
                log.debug("tenant_filter_enabled: tenant={} session={}", tid, System.identityHashCode(session));
            } else {
                log.debug("tenant_filter_already_enabled: tenant={}", tid);
            }
        } catch (Exception e) {
            log.warn("tenant_filter_enable_failed: {}", e.toString());
        }

        return pjp.proceed();
    }
}
