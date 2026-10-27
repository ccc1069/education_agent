package com.edu.agent.controller;

import com.edu.agent.core.AgentEvent;
import com.edu.agent.core.EventHistoryService;
import com.edu.agent.core.EventType;
import com.edu.agent.core.KnowledgeGraph;
import com.edu.agent.core.LearnerModel;
import com.edu.agent.db.entity.User;
import com.edu.agent.db.enums.UserRole;
import com.edu.agent.security.PrincipalUser;
import com.edu.agent.security.SecurityContextHelper;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 学习者路由 -- 对齐 Python /api/v1/{submit,question,message,progress,knowledge-graph}。
 * 学习者 ID 从 JWT 推断,不再放 body。
 */
@Slf4j
@RestController
@RequestMapping("/api/v1")
@RequiredArgsConstructor
public class LearnerController {

    private final ApplicationEventPublisher publisher;
    private final EventHistoryService historyService;
    private final KnowledgeGraph knowledgeGraph;
    private final SecurityContextHelper securityContext;
    private final com.edu.agent.service.LearnerModelService learnerModelService;

    public record SubmitAnswerRequest(
            @NotBlank String knowledge_id,
            @NotNull Boolean is_correct,
            Double time_spent_seconds
    ) {}

    public record AskQuestionRequest(
            @NotBlank String knowledge_id,
            @NotBlank @Size(max = 2000) String question,
            Boolean debate_mode
    ) {}

    public record SendMessageRequest(
            @NotBlank @Size(max = 4000) String message,
            String knowledge_id
    ) {}

    @GetMapping("/health")
    public Map<String, Object> health() {
        return Map.of(
                "status", "ok",
                "service", "multi-agent-education-java",
                "agents", 5
        );
    }

    @PostMapping("/submit")
    @PreAuthorize("hasRole('STUDENT')")
    public Map<String, Object> submitAnswer(@Valid @RequestBody SubmitAnswerRequest req) {
        PrincipalUser principal = securityContext.require();
        String learnerPublicId = principal.getLearnerPublicId();
        double timeSpent = req.time_spent_seconds() != null ? req.time_spent_seconds() : 0.0;

        Map<String, Object> data = new HashMap<>();
        data.put("knowledge_id", req.knowledge_id());
        data.put("is_correct", req.is_correct());
        data.put("time_spent_seconds", timeSpent);

        learnerModelService.recordSubmission(
                learnerPublicId, req.knowledge_id(), req.is_correct(), timeSpent);
        publisher.publishEvent(new AgentEvent(
                this, EventType.STUDENT_SUBMISSION, "api", learnerPublicId, data));
        learnerModelService.save(learnerPublicId);

        List<AgentEvent> events = historyService.getHistory(learnerPublicId, null, 10);
        return Map.of(
                "status", "processed",
                "events_triggered", events.size(),
                "events", formatEvents(events)
        );
    }

    @PostMapping("/question")
    @PreAuthorize("hasRole('STUDENT')")
    public Map<String, Object> askQuestion(@Valid @RequestBody AskQuestionRequest req) {
        PrincipalUser principal = securityContext.require();
        String learnerPublicId = principal.getLearnerPublicId();

        Map<String, Object> data = new HashMap<>();
        data.put("knowledge_id", req.knowledge_id());
        data.put("question", req.question());
        data.put("debate_mode", Boolean.TRUE.equals(req.debate_mode()));

        publisher.publishEvent(new AgentEvent(
                this, EventType.STUDENT_QUESTION, "api", learnerPublicId, data));

        List<AgentEvent> events = historyService.getHistory(learnerPublicId, null, 10);
        return Map.of(
                "status", "processed",
                "events_triggered", events.size(),
                "events", formatEvents(events)
        );
    }

    @PostMapping("/message")
    @PreAuthorize("hasRole('STUDENT')")
    public Map<String, Object> sendMessage(@Valid @RequestBody SendMessageRequest req) {
        PrincipalUser principal = securityContext.require();
        String learnerPublicId = principal.getLearnerPublicId();
        String knowledgeId = req.knowledge_id() != null ? req.knowledge_id() : "general";

        Map<String, Object> data = new HashMap<>();
        data.put("message", req.message());
        data.put("knowledge_id", knowledgeId);

        publisher.publishEvent(new AgentEvent(
                this, EventType.STUDENT_MESSAGE, "api", learnerPublicId, data));

        List<AgentEvent> events = historyService.getHistory(learnerPublicId, null, 10);
        return Map.of(
                "status", "processed",
                "events_triggered", events.size(),
                "events", formatEvents(events)
        );
    }

    @GetMapping("/progress/{learnerPublicId}")
    public Map<String, Object> getProgress(@PathVariable String learnerPublicId) {
        PrincipalUser principal = securityContext.require();
        if (principal.hasRole(UserRole.STUDENT) && !learnerPublicId.equals(principal.getLearnerPublicId())) {
            throw new AccessDeniedException("学生只能查看自己的学习进度");
        }

        LearnerModel model = learnerModelService.getOrLoad(learnerPublicId);
        if (model.getStatesView().isEmpty()) {
            return Map.of("learner_id", learnerPublicId, "status", "no_data");
        }

        Map<String, Object> progress = new HashMap<>();
        for (var entry : model.getStatesView().entrySet()) {
            progress.put(entry.getKey(), entry.getValue().getMastery());
        }

        List<Map<String, Object>> weakPoints = model.getWeakPoints(0.3).stream()
                .map(s -> Map.<String, Object>of("id", s.getKnowledgeId(), "mastery", s.getMastery()))
                .toList();
        List<Map<String, Object>> strongPoints = model.getStrongPoints(0.85).stream()
                .map(s -> Map.<String, Object>of("id", s.getKnowledgeId(), "mastery", s.getMastery()))
                .toList();

        return Map.of(
                "learner_id", learnerPublicId,
                "progress", progress,
                "overall", model.getOverallProgress(),
                "weak_points", weakPoints,
                "strong_points", strongPoints
        );
    }

    @GetMapping("/knowledge-graph")
    public Map<String, Object> getKnowledgeGraph() {
        List<Map<String, Object>> nodes = knowledgeGraph.getNodes().values().stream()
                .map(n -> {
                    Map<String, Object> m = new HashMap<>();
                    m.put("id", n.id());
                    m.put("name", n.name());
                    m.put("difficulty", n.difficulty());
                    m.put("prerequisites", n.prerequisites());
                    m.put("tags", n.tags());
                    return m;
                })
                .toList();
        return Map.of(
                "nodes", nodes,
                "learning_order", knowledgeGraph.topologicalSort()
        );
    }

    @GetMapping("/events/{learnerPublicId}")
    public Map<String, Object> getEvents(@PathVariable String learnerPublicId,
                                         @RequestParam(required = false) String type,
                                         @RequestParam(defaultValue = "20") int limit) {
        PrincipalUser principal = securityContext.require();
        if (principal.hasRole(UserRole.STUDENT) && !learnerPublicId.equals(principal.getLearnerPublicId())) {
            throw new AccessDeniedException("学生只能查看自己的事件历史");
        }
        EventType filter = type != null ? EventType.fromWire(type) : null;
        List<AgentEvent> events = historyService.getHistory(learnerPublicId, filter, limit);
        return Map.of(
                "learner_id", learnerPublicId,
                "events", formatEvents(events)
        );
    }

    private List<Map<String, Object>> formatEvents(List<AgentEvent> events) {
        return events.stream()
                .map(e -> {
                    Map<String, Object> m = new HashMap<>();
                    m.put("type", e.getType().getWireName());
                    m.put("source", e.getSourceName());
                    m.put("data", e.getData());
                    m.put("correlation_id", e.getCorrelationId());
                    return m;
                })
                .toList();
    }
}
