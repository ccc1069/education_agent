package com.edu.agent.db.repository;

import com.edu.agent.db.entity.User;
import com.edu.agent.db.enums.UserRole;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;
import java.util.List;
import java.util.Optional;

@Repository
public interface UserRepository extends JpaRepository<User, BigInteger> {
    Optional<User> findByEmail(String email);
    List<User> findByTenantIdAndRole(BigInteger tenantId, UserRole role);
    boolean existsByEmail(String email);
    long countByTenantId(BigInteger tenantId);
}
