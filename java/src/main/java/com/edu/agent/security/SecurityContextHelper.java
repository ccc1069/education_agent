package com.edu.agent.security;

import lombok.extern.slf4j.Slf4j;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

import java.math.BigInteger;
import java.util.Optional;

/**
 * 当前用户上下文访问工具。
 * 在任意业务代码中通过 SecurityContextHelper.current() 获取已认证用户。
 */
@Slf4j
@Component
public class SecurityContextHelper {

    public Optional<PrincipalUser> current() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth == null || !auth.isAuthenticated()) {
            return Optional.empty();
        }
        Object p = auth.getPrincipal();
        if (p instanceof PrincipalUser pu) {
            return Optional.of(pu);
        }
        return Optional.empty();
    }

    public PrincipalUser require() {
        return current().orElseThrow(() -> new IllegalStateException("当前线程无认证用户"));
    }

    public BigInteger requireUserId() {
        return require().getId();
    }

    public BigInteger requireTenantId() {
        return require().getTenantId();
    }

    public boolean isAdmin() {
        return current().map(p -> p.hasRole(com.edu.agent.db.enums.UserRole.ADMIN)).orElse(false);
    }

    public boolean isTeacher() {
        return current().map(p -> p.hasRole(com.edu.agent.db.enums.UserRole.TEACHER)).orElse(false);
    }

    public boolean isStudent() {
        return current().map(p -> p.hasRole(com.edu.agent.db.enums.UserRole.STUDENT)).orElse(false);
    }
}
