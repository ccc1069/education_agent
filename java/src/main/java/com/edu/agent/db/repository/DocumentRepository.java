package com.edu.agent.db.repository;

import com.edu.agent.db.entity.Document;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;
import java.util.Optional;

@Repository
public interface DocumentRepository extends JpaRepository<Document, BigInteger> {
    Optional<Document> findByContentHash(String contentHash);
    Page<Document> findByTenantIdOrderByCreatedAtDesc(BigInteger tenantId, Pageable pageable);
    Page<Document> findByTenantIdAndStatus(BigInteger tenantId, String status, Pageable pageable);
}
