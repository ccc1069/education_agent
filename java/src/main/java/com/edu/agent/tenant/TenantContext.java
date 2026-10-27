package com.edu.agent.tenant;

import java.math.BigInteger;

/**
 * 租户上下文 -- 对齐 Python core/tenant_context.py。
 *
 * ThreadLocal 持有当前请求的 tenant_id:
 *   - null: 跨租户(平台管理员操作,跳过过滤)
 *   - BigInteger: 当前租户 ID
 *
 * 由 TenantContextFilter 在请求开始时从 JWT 读取并设置,
 * 在请求结束时 clear() 清理,避免线程池泄漏。
 */
public final class TenantContext {

    private static final ThreadLocal<BigInteger> CURRENT = new ThreadLocal<>();

    private TenantContext() {}

    public static BigInteger get() {
        return CURRENT.get();
    }

    public static void set(BigInteger tenantId) {
        CURRENT.set(tenantId);
    }

    public static void clear() {
        CURRENT.remove();
    }

    public static boolean isCrossTenant() {
        return CURRENT.get() == null;
    }
}
