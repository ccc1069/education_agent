package com.edu.agent.controller;

import com.edu.agent.db.enums.UserRole;
import com.edu.agent.security.PrincipalUser;
import com.edu.agent.security.SecurityContextHelper;
import com.edu.agent.service.QuestionService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * 题目路由 -- 对齐 Python /api/v1/questions/*。
 * - 生成/审核/删除: 教师/管理员
 * - 列表/详情: 所有认证用户(详情按角色隐藏答案)
 * - 校验答案: 所有认证用户(仅 published)
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/questions")
@RequiredArgsConstructor
public class QuestionController {

    private final QuestionService questionService;
    private final SecurityContextHelper securityContext;

    public record GenerateQuestionRequest(
            @NotBlank @Size(max = 64) String knowledge_id,
            String question_type,
            @Min(1) @Max(5) Integer difficulty,
            Boolean use_rag
    ) {}

    public record ReviewQuestionRequest(@NotBlank String new_status) {}

    public record VerifyAnswerRequest(@NotBlank @Size(max = 2000) String student_answer) {}

    @PostMapping("/generate")
    @PreAuthorize("hasAnyRole('TEACHER','ADMIN')")
    @ResponseStatus(HttpStatus.CREATED)
    public Map<String, Object> generate(@Valid @RequestBody GenerateQuestionRequest req) {
        PrincipalUser p = securityContext.require();
        return Map.of(
                "success", true,
                "data", questionService.generateQuestion(
                        req.knowledge_id(),
                        req.question_type(),
                        req.difficulty() != null ? req.difficulty() : 3,
                        p.getId() != null ? p.getId().intValue() : null,
                        Boolean.TRUE.equals(req.use_rag())
                )
        );
    }

    @GetMapping
    public Map<String, Object> list(
            @RequestParam(name = "status", required = false) String status,
            @RequestParam(name = "knowledge_id", required = false) String knowledgeId,
            @RequestParam(name = "question_type", required = false) String questionType,
            @RequestParam(name = "difficulty", required = false) Integer difficulty,
            @RequestParam(defaultValue = "50") int limit,
            @RequestParam(defaultValue = "0") int offset) {
        PrincipalUser p = securityContext.require();
        Page<Map<String, Object>> page = questionService.listQuestions(
                p.getTenantId(), status, knowledgeId, questionType, difficulty, limit, offset);
        return Map.of(
                "success", true,
                "data", page.getContent(),
                "meta", Map.of(
                        "total", page.getTotalElements(),
                        "limit", limit,
                        "offset", offset
                )
        );
    }

    @GetMapping("/{questionId}")
    public Map<String, Object> get(@PathVariable java.math.BigInteger questionId) {
        PrincipalUser p = securityContext.require();
        boolean isStaff = p.hasRole(UserRole.TEACHER) || p.hasRole(UserRole.ADMIN);
        Map<String, Object> q = questionService.getQuestion(questionId, isStaff);
        if (q == null) {
            return Map.of("success", false, "error", "NOT_FOUND");
        }
        if (p.hasRole(UserRole.STUDENT) && !"published".equals(q.get("status"))) {
            throw new org.springframework.security.access.AccessDeniedException(
                    "学生无法访问此题目");
        }
        return Map.of("success", true, "data", q);
    }

    @PostMapping("/{questionId}/status")
    @PreAuthorize("hasAnyRole('TEACHER','ADMIN')")
    public Map<String, Object> review(@PathVariable java.math.BigInteger questionId,
                                      @Valid @RequestBody ReviewQuestionRequest req) {
        PrincipalUser p = securityContext.require();
        Map<String, Object> result = questionService.reviewQuestion(
                questionId, req.new_status(),
                p.getId() != null ? p.getId().intValue() : null);
        if (result == null) {
            return Map.of("success", false, "error", "NOT_FOUND");
        }
        return Map.of("success", true, "data", result);
    }

    @PostMapping("/{questionId}/delete")
    @PreAuthorize("hasAnyRole('TEACHER','ADMIN')")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable java.math.BigInteger questionId) {
        if (!questionService.deleteQuestion(questionId)) {
            throw new IllegalArgumentException("题目不存在");
        }
    }

    @PostMapping("/{questionId}/check")
    public Map<String, Object> check(@PathVariable java.math.BigInteger questionId,
                                     @Valid @RequestBody VerifyAnswerRequest req) {
        Map<String, Object> result = questionService.verifyAnswer(questionId, req.student_answer());
        if (result == null) {
            return Map.of("success", false, "error", "NOT_FOUND");
        }
        return Map.of("success", true, "data", result);
    }
}
