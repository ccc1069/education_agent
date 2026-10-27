package com.edu.agent.controller;

import com.edu.agent.security.SecurityContextHelper;
import com.edu.agent.service.RagService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 知识库路由 -- 对齐 Python /api/v1/knowledge-base/*（响应体不包 success/data）。
 * - 上传/删除: 教师/管理员
 * - 列表/详情/检索: 所有认证用户
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/knowledge-base")
@RequiredArgsConstructor
public class RagController {

    private final RagService ragService;
    private final SecurityContextHelper securityContext;

    public record UploadDocumentRequest(
            @NotBlank @Size(max = 256) String title,
            @NotBlank @Size(max = 100_000) String content,
            @Size(max = 32) String source_type,
            @Size(max = 512) String source_url,
            Map<String, Object> metadata
    ) {}

    public record SearchRequest(
            @NotBlank @Size(max = 2000) String query,
            @Min(1) @Max(20) Integer top_k,
            @Min(0) @Max(1) Double min_score
    ) {}

    @PostMapping("/documents")
    @PreAuthorize("hasAnyRole('TEACHER','ADMIN')")
    @ResponseStatus(HttpStatus.CREATED)
    public Map<String, Object> upload(@Valid @RequestBody UploadDocumentRequest req) {
        securityContext.require();
        RagService.IngestResult result = ragService.ingestDocument(
                req.title(), req.content(), req.source_type(), req.source_url(), req.metadata());
        return Map.of(
                "document_id", result.documentId(),
                "is_new", result.isNew(),
                "message", result.isNew()
                        ? "Document uploaded and indexed"
                        : "Document already exists (deduplicated)"
        );
    }

    @GetMapping("/documents")
    public List<Map<String, Object>> list(@RequestParam(name = "status", required = false) String status,
                                          @RequestParam(defaultValue = "50") int limit,
                                          @RequestParam(defaultValue = "0") int offset) {
        var tenantId = securityContext.requireTenantId();
        return ragService.listDocuments(tenantId, status, limit, offset);
    }

    @GetMapping("/documents/{documentId}")
    public Map<String, Object> get(@PathVariable java.math.BigInteger documentId) {
        Map<String, Object> doc = ragService.getDocument(documentId);
        if (doc == null) {
            throw new IllegalArgumentException("文档不存在");
        }
        return doc;
    }

    @PostMapping("/documents/{documentId}/delete")
    @PreAuthorize("hasAnyRole('TEACHER','ADMIN')")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable java.math.BigInteger documentId) {
        if (!ragService.deleteDocument(documentId)) {
            throw new IllegalArgumentException("文档不存在");
        }
    }

    @PostMapping("/search")
    public List<Map<String, Object>> search(@Valid @RequestBody SearchRequest req) {
        var tenantId = securityContext.requireTenantId();
        int topK = req.top_k() != null ? req.top_k() : 5;
        double minScore = req.min_score() != null ? req.min_score() : 0.0;
        return ragService.search(tenantId, req.query(), topK, minScore);
    }
}
