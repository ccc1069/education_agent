package com.edu.agent.controller;

import com.edu.agent.security.SecurityContextHelper;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Vision 路由 -- 对齐 Python /api/v1/vision/analyze。
 * 当前实现为 stub(无 LLM vision),返回固定提示。后续接入多模态 LLM 后扩展。
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/vision")
@RequiredArgsConstructor
public class VisionController {

    private final SecurityContextHelper securityContext;

    public record VisionAnalyzeRequest(
            @NotEmpty @Size(max = 4) List<String> images,
            @Size(max = 64) String knowledge_id,
            @Size(max = 500) String learner_message,
            String level,
            @Min(0) @Max(1) Double mastery
    ) {}

    @PostMapping("/analyze")
    public Map<String, Object> analyze(@Valid @RequestBody VisionAnalyzeRequest req) {
        securityContext.require();
        log.info("Vision analyze: images={} knowledge={}", req.images().size(), req.knowledge_id());

        // Stub response: 实际实现需调用 VisionTutorService.analyze_image(...)
        String response = "（视觉分析服务暂未接入多模态 LLM,这是 stub 响应。) "
                + "已收到 " + req.images().size() + " 张图片,知识点: "
                + (req.knowledge_id() != null ? req.knowledge_id() : "general");

        Map<String, Object> meta = new HashMap<>();
        meta.put("image_count", req.images().size());
        meta.put("knowledge_id", req.knowledge_id());
        meta.put("level", req.level() != null ? req.level() : "beginner");
        meta.put("mastery", req.mastery() != null ? req.mastery() : 0.0);
        meta.put("stub", true);

        return Map.of(
                "success", true,
                "data", Map.of(
                        "response", response,
                        "metadata", meta
                )
        );
    }
}
