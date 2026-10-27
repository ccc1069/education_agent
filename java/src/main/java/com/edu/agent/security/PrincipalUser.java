package com.edu.agent.security;

import com.edu.agent.db.entity.User;
import com.edu.agent.db.enums.UserRole;
import lombok.Getter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

import java.math.BigInteger;
import java.util.Collection;
import java.util.List;

/**
 * 安全上下文中的当前用户主体。
 * 对齐 Python CurrentUser(id/email/role/tenant_id/learner_public_id)。
 */
@Getter
public class PrincipalUser implements UserDetails {

    private final BigInteger id;
    private final String email;
    private final UserRole role;
    private final BigInteger tenantId;
    private final String learnerPublicId;
    private final boolean active;

    public PrincipalUser(User user, String learnerPublicId) {
        this.id = user.getId();
        this.email = user.getEmail();
        this.role = user.getRole();
        this.tenantId = user.getTenantId();
        this.learnerPublicId = learnerPublicId;
        this.active = Boolean.TRUE.equals(user.getIsActive());
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return List.of(new SimpleGrantedAuthority("ROLE_" + role.name()));
    }

    @Override
    public String getPassword() {
        return "";
    }

    @Override
    public String getUsername() {
        return email;
    }

    @Override
    public boolean isAccountNonExpired() { return true; }

    @Override
    public boolean isAccountNonLocked() { return true; }

    @Override
    public boolean isCredentialsNonExpired() { return true; }

    @Override
    public boolean isEnabled() { return active; }

    public boolean hasRole(UserRole required) {
        return role == required;
    }
}
