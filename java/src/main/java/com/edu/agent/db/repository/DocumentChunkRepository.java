package com.edu.agent.db.repository;

import com.edu.agent.db.entity.DocumentChunk;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;
import java.util.List;

@Repository
public interface DocumentChunkRepository extends JpaRepository<DocumentChunk, BigInteger> {
    List<DocumentChunk> findByDocumentIdOrderByChunkIndex(BigInteger documentId);
    List<DocumentChunk> findByTenantId(BigInteger tenantId);
}
