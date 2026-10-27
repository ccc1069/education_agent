package com.edu.agent.tenant;

import lombok.extern.slf4j.Slf4j;
import org.hibernate.Filter;
import org.hibernate.Session;
import org.springframework.stereotype.Component;

import java.math.BigInteger;

/**
 * 租户过滤器助手 -- 启用 Hibernate 的 tenant_filter,绑定参数。
 *
 * 使用方式: 在 Service 层注入后,在每个 @Transactional 方法首次访问 Session 时调用 enable();
 * 更推荐的做法是在一个 AspectJ 切面里环绕 Repository 调用。
 *
 * 简化版: 通过 Hibernate 的 Interceptor 自动在 Session 创建时启用。
 */
@Slf4j
@Component
public class TenantFilterHelper {

    public static final String FILTER_NAME = "tenantFilter";
    public static final String FILTER_PARAM = "tenantId";

    /**
     * 启用 tenant_filter。
     * 跨租户(ADMIN 且无 X-Tenant-ID)时跳过,允许全租户查询。
     */
    public void enable(Session session) {
        BigInteger tid = TenantContext.get();
        if (tid == null) return; // 跨租户
        Filter filter = session.enableFilter(FILTER_NAME);
        filter.setParameter(FILTER_PARAM, tid);
    }

    public void disable(Session session) {
        if (session.getEnabledFilter(FILTER_NAME) != null) {
            session.disableFilter(FILTER_NAME);
        }
    }
}
