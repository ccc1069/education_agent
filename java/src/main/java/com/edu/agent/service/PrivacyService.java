package com.edu.agent.service;

import com.edu.agent.db.entity.DataExportJob;
import com.edu.agent.db.entity.PrivacyConsent;
import com.edu.agent.db.entity.PrivacyDeletionRequest;
import com.edu.agent.db.repository.DataExportJobRepository;
import com.edu.agent.db.repository.PrivacyConsentRepository;
import com.edu.agent.db.repository.PrivacyDeletionRequestRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigInteger;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 隐私服务 -- 对齐 Python services/privacy_service.py。
 * - 同意管理(4 种类型)
 * - 数据导出(stub: 立即完成,无实际打包)
 * - 账户删除(soft delete,7 天后实际执行)
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class PrivacyService {

    private final PrivacyConsentRepository consentRepository;
    private final PrivacyDeletionRequestRepository deletionRequestRepository;
    private final DataExportJobRepository exportJobRepository;

    private static final Set<String> VALID_CONSENT_TYPES = Set.of(
            "analytics", "llm_training", "marketing", "third_party_share"
    );

    @Transactional(readOnly = true)
    public Map<String, Boolean> getConsentStatus(BigInteger userId) {
        Map<String, Boolean> status = new HashMap<>();
        for (String type : VALID_CONSENT_TYPES) {
            status.put(type, consentRepository
                    .findFirstByUserIdAndConsentTypeOrderByCreatedAtDesc(userId, type)
                    .map(PrivacyConsent::getGranted)
                    .orElse(false));
        }
        return status;
    }

    @Transactional
    public PrivacyConsent setConsent(BigInteger userId, String consentType, boolean granted,
                                       String ip, String userAgent) {
        if (!VALID_CONSENT_TYPES.contains(consentType)) {
            throw new IllegalArgumentException("无效的同意类型: " + consentType);
        }
        PrivacyConsent consent = new PrivacyConsent();
        consent.setUserId(userId);
        consent.setConsentType(consentType);
        consent.setGranted(granted);
        consent.setConsentVersion("1.0");
        consent.setIp(ip != null ? ip : "");
        consent.setUserAgent(userAgent != null ? userAgent : "");
        return consentRepository.save(consent);
    }

    @Transactional
    public DataExportJob requestExport(BigInteger userId) {
        DataExportJob job = new DataExportJob();
        job.setUserId(userId);
        job.setStatus("pending");
        job = exportJobRepository.save(job);
        // Stub: 立即标记完成。实际实现应异步打包后更新 download_url + file_size_bytes。
        job.setStatus("completed");
        job.setCompletedAt(Instant.now());
        job.setDownloadUrl("/api/v1/privacy/export/" + job.getId() + "/download");
        job.setFileSizeBytes(0);
        return exportJobRepository.save(job);
    }

    @Transactional(readOnly = true)
    public List<DataExportJob> listExports(BigInteger userId) {
        return exportJobRepository.findByUserIdOrderByRequestedAtDesc(userId);
    }

    @Transactional
    public PrivacyDeletionRequest requestDeletion(BigInteger userId, String reason) {
        PrivacyDeletionRequest req = new PrivacyDeletionRequest();
        req.setUserId(userId);
        req.setStatus("pending");
        req.setReason(reason != null ? reason : "");
        req.setScheduledAt(Instant.now().plusSeconds(7 * 24 * 3600L));
        return deletionRequestRepository.save(req);
    }

    @Transactional(readOnly = true)
    public List<PrivacyDeletionRequest> listDeletionRequests(BigInteger userId) {
        return deletionRequestRepository.findByUserIdOrderByRequestedAtDesc(userId);
    }

    @Transactional
    public boolean cancelDeletion(BigInteger userId, BigInteger requestId) {
        return deletionRequestRepository.findById(requestId).map(req -> {
            if (!req.getUserId().equals(userId)) return false;
            if (!"pending".equals(req.getStatus())) return false;
            req.setStatus("cancelled");
            req.setCancelledAt(Instant.now());
            deletionRequestRepository.save(req);
            return true;
        }).orElse(false);
    }
}
