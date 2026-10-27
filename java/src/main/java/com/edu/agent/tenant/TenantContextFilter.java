package com.edu.agent.tenant;

import com.edu.agent.security.PrincipalUser;
import com.edu.agent.security.SecurityContextHelper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.math.BigInteger;

/**
 * 租户识别过滤器 -- 对齐 Python TenantMiddleware。
 *
 * 优先级:
 *   1. X-Tenant-ID 头(仅 ADMIN 可跨租户)
 *   2. JWT 中的 tenant_id
 *   3. null(未认证 -> 跳过过滤,由 RBAC 阻断)
 *
 * 在 SecurityContext 之后执行(通过 @Order),因此能读到 PrincipalUser。
 * 请求结束必须 clear(),否则线程池复用会泄漏租户状态。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class TenantContextFilter extends OncePerRequestFilter {

    private final SecurityContextHelper securityContext;

    @Override
    protected void doFilterInternal(HttpServletRequest req, HttpServletResponse resp, FilterChain chain)
            throws ServletException, IOException {
        try {
            PrincipalUser p = securityContext.current().orElse(null);
            if (p == null) {
                // 未认证,由 RBAC 阻断,这里不设租户
                chain.doFilter(req, resp);
                return;
            }

            String headerTenant = req.getHeader("X-Tenant-ID");
            if (headerTenant != null && !headerTenant.isBlank()) {
                try {
                    BigInteger tid = new BigInteger(headerTenant.trim());
                    if (!p.hasRole(com.edu.agent.db.enums.UserRole.ADMIN)) {
                        // 非管理员只能用自己租户
                        if (!tid.equals(p.getTenantId())) {
                            resp.setStatus(HttpServletResponse.SC_FORBIDDEN);
                            resp.getWriter().write("{\"detail\":\"跨租户操作需管理员权限\"}");
                            return;
                        }
                    }
                    TenantContext.set(tid);
                } catch (NumberFormatException e) {
                    log.warn("invalid X-Tenant-ID header: {}", headerTenant);
                    TenantContext.set(p.getTenantId());
                }
            } else {
                // 默认: 用户的 tenant_id
                TenantContext.set(p.getTenantId());
            }
            chain.doFilter(req, resp);
        } finally {
            TenantContext.clear();
        }
    }
}
