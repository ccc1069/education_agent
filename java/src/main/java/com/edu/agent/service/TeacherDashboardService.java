package com.edu.agent.service;

import com.edu.agent.db.entity.ClassMember;
import com.edu.agent.db.entity.ClassRoom;
import com.edu.agent.db.entity.KnowledgeState;
import com.edu.agent.db.repository.ClassMemberRepository;
import com.edu.agent.db.repository.ClassRoomRepository;
import com.edu.agent.db.repository.KnowledgeStateRepository;
import com.edu.agent.db.repository.LearnerRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigInteger;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * 教师看板服务 -- 对齐 Python services/teacher_dashboard_service.py。
 * - 平均掌握度: 全班 KnowledgeState mastery 平均
 * - 薄弱知识点: avg(mastery) < 0.4(Top 10)
 * - 干预推荐: mastery < 0.2 且 attempts >= 3 的学生(Top 20)
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class TeacherDashboardService {

    private final ClassRoomRepository classRoomRepository;
    private final ClassMemberRepository classMemberRepository;
    private final KnowledgeStateRepository knowledgeStateRepository;
    private final LearnerRepository learnerRepository;

    @Transactional(readOnly = true)
    public Map<String, Object> getClassDashboard(BigInteger classId) {
        ClassRoom cls = classRoomRepository.findById(classId).orElse(null);
        if (cls == null) return null;

        List<ClassMember> members = classMemberRepository.findByClassId(classId);
        List<BigInteger> learnerIds = members.stream().map(ClassMember::getLearnerId).toList();

        List<KnowledgeState> states = learnerIds.stream()
                .flatMap(lid -> knowledgeStateRepository.findByLearnerId(lid).stream())
                .toList();

        double avgMastery = states.stream()
                .mapToDouble(KnowledgeState::getMastery)
                .average()
                .orElse(0.0);

        // 薄弱知识点: 按 knowledge_id 聚合, avg < 0.4, Top 10
        Map<String, double[]> byKnowledge = new HashMap<>();
        for (KnowledgeState s : states) {
            double[] agg = byKnowledge.computeIfAbsent(s.getKnowledgeId(),
                    k -> new double[]{0.0, 0.0});
            agg[0] += s.getMastery();
            agg[1] += 1;
        }
        List<Map<String, Object>> weak = byKnowledge.entrySet().stream()
                .map(e -> {
                    double avg = e.getValue()[1] > 0 ? e.getValue()[0] / e.getValue()[1] : 0;
                    Map<String, Object> m = new HashMap<>();
                    m.put("knowledge_id", e.getKey());
                    m.put("avg_mastery", avg);
                    m.put("sample_count", (int) e.getValue()[1]);
                    return m;
                })
                .filter(m -> (double) m.get("avg_mastery") < 0.4)
                .sorted((a, b) -> Double.compare((double) a.get("avg_mastery"), (double) b.get("avg_mastery")))
                .limit(10)
                .collect(Collectors.toList());

        // 干预推荐: mastery < 0.2 且 attempts >= 3
        List<Map<String, Object>> interventions = states.stream()
                .filter(s -> s.getMastery() < 0.2 && s.getAttempts() >= 3)
                .sorted((a, b) -> Double.compare(a.getMastery(), b.getMastery()))
                .limit(20)
                .map(s -> {
                    Map<String, Object> m = new HashMap<>();
                    m.put("learner_id", s.getLearnerId());
                    m.put("knowledge_id", s.getKnowledgeId());
                    m.put("mastery", s.getMastery());
                    m.put("attempts", s.getAttempts());
                    learnerRepository.findById(s.getLearnerId())
                            .ifPresent(l -> m.put("learner_name", l.getName()));
                    return m;
                })
                .collect(Collectors.toList());

        Map<String, Object> result = new HashMap<>();
        result.put("class_id", classId);
        result.put("class_name", cls.getName());
        result.put("member_count", members.size());
        result.put("total_states", states.size());
        result.put("avg_mastery", avgMastery);
        result.put("weak_knowledge_ids", weak);
        result.put("interventions", interventions);
        return result;
    }
}
