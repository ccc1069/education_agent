package com.edu.agent.db.repository;

import com.edu.agent.db.entity.DataExportJob;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;
import java.util.List;

@Repository
public interface DataExportJobRepository extends JpaRepository<DataExportJob, BigInteger> {
    List<DataExportJob> findByUserIdOrderByRequestedAtDesc(BigInteger userId);
    List<DataExportJob> findByStatus(String status);
}
