package com.edu.agent.service;

import com.edu.agent.db.entity.Assignment;
import com.edu.agent.db.entity.ClassMember;
import com.edu.agent.db.entity.ClassRoom;
import com.edu.agent.db.entity.Question;
import com.edu.agent.db.repository.AssignmentRepository;
import com.edu.agent.db.repository.ClassMemberRepository;
import com.edu.agent.db.repository.ClassRoomRepository;
import com.edu.agent.db.repository.QuestionRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigInteger;
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 作业服务 -- 对齐 Python services/assignment_service.py。
 * 状态机: draft -> published -> closed -> archived。
 * - 创建: 校验教师拥有班级 + 题目已 published
 * - 更新: 仅 draft 可改 question_ids / class_id
 * - 状态迁移: draft -> published, published -> closed, closed -> archived
 * - 删除: 仅 draft 可删
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AssignmentService {

    private final AssignmentRepository assignmentRepository;
    private final ClassRoomRepository classRoomRepository;
    private final ClassMemberRepository classMemberRepository;
    private final QuestionRepository questionRepository;

    @Transactional
    public Map<String, Object> createAssignment(String title, BigInteger classId, BigInteger teacherId,
                                                 List<BigInteger> questionIds, String description,
                                                 Instant dueAt, boolean allowCrossTeacher) {
        ClassRoom cls = classRoomRepository.findById(classId)
                .orElseThrow(() -> new IllegalArgumentException("班级不存在"));
        if (!allowCrossTeacher && !cls.getTeacherId().equals(teacherId)) {
            throw new IllegalArgumentException("只能为自己的班级布置作业");
        }
        validateQuestions(questionIds);
        Assignment a = new Assignment();
        a.setTitle(title);
        a.setClassId(classId);
        a.setTeacherId(teacherId);
        a.setQuestionIds(questionIds);
        a.setDescription(description != null ? description : "");
        a.setDueAt(dueAt);
        a.setStatus("draft");
        a = assignmentRepository.save(a);
        return toMap(a);
    }

    @Transactional(readOnly = true)
    public List<Map<String, Object>> listTeacherAssignments(BigInteger teacherId, String status) {
        List<Assignment> list = status != null && !status.isBlank()
                ? assignmentRepository.findByTeacherIdAndStatus(teacherId, status)
                : assignmentRepository.findByTeacherId(teacherId);
        return list.stream().map(this::toMap).toList();
    }

    @Transactional(readOnly = true)
    public List<Map<String, Object>> listAllAssignments(String status) {
        List<Assignment> list;
        if (status != null && !status.isBlank()) {
            list = assignmentRepository.findByTenantIdAndStatus(BigInteger.ONE, status);
        } else {
            list = assignmentRepository.findByTenantId(BigInteger.ONE);
        }
        return list.stream().map(this::toMap).toList();
    }

    @Transactional(readOnly = true)
    public List<Map<String, Object>> listClassAssignments(BigInteger classId, String status) {
        List<Assignment> list = status != null && !status.isBlank()
                ? assignmentRepository.findByClassIdAndStatus(classId, status)
                : assignmentRepository.findByClassId(classId);
        return list.stream().map(this::toMap).toList();
    }

    @Transactional(readOnly = true)
    public List<Map<String, Object>> listLearnerAssignments(BigInteger learnerId) {
        List<ClassMember> memberships = classMemberRepository.findByLearnerId(learnerId);
        Set<BigInteger> classIds = new HashSet<>();
        for (ClassMember m : memberships) classIds.add(m.getClassId());
        return assignmentRepository.findAll().stream()
                .filter(a -> classIds.contains(a.getClassId()))
                .filter(a -> "published".equals(a.getStatus()) || "closed".equals(a.getStatus()))
                .map(this::toMap)
                .toList();
    }

    @Transactional(readOnly = true)
    public Map<String, Object> getAssignment(BigInteger id) {
        return assignmentRepository.findById(id).map(this::toMap).orElse(null);
    }

    @Transactional
    public Map<String, Object> updateAssignment(BigInteger id, String title, String description,
                                                 List<BigInteger> questionIds, Instant dueAt,
                                                 BigInteger classId, boolean allowCrossTeacher,
                                                 BigInteger teacherId) {
        Assignment a = assignmentRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Assignment not found"));
        if (!allowCrossTeacher && !a.getTeacherId().equals(teacherId)) {
            throw new IllegalArgumentException("只能编辑自己布置的作业");
        }
        if (!"draft".equals(a.getStatus())) {
            throw new IllegalArgumentException("仅草稿状态可编辑内容(状态: " + a.getStatus() + ")");
        }
        if (classId != null && !classId.equals(a.getClassId())) {
            ClassRoom cls = classRoomRepository.findById(classId)
                    .orElseThrow(() -> new IllegalArgumentException("班级不存在"));
            if (!allowCrossTeacher && !cls.getTeacherId().equals(teacherId)) {
                throw new IllegalArgumentException("只能转入自己的班级");
            }
            a.setClassId(classId);
        }
        if (questionIds != null && !questionIds.isEmpty()) {
            validateQuestions(questionIds);
            a.setQuestionIds(questionIds);
        }
        a.setTitle(title);
        a.setDescription(description != null ? description : "");
        a.setDueAt(dueAt);
        a = assignmentRepository.save(a);
        return toMap(a);
    }

    @Transactional
    public Map<String, Object> updateStatus(BigInteger id, String newStatus) {
        Assignment a = assignmentRepository.findById(id).orElse(null);
        if (a == null) return null;
        String current = a.getStatus();
        if (!isValidTransition(current, newStatus)) {
            throw new IllegalArgumentException("不允许的状态迁移: " + current + " -> " + newStatus);
        }
        a.setStatus(newStatus);
        a = assignmentRepository.save(a);
        return toMap(a);
    }

    @Transactional
    public boolean deleteAssignment(BigInteger id) {
        Assignment a = assignmentRepository.findById(id).orElse(null);
        if (a == null) return false;
        if (!"draft".equals(a.getStatus())) {
            throw new IllegalArgumentException("仅草稿状态可删除");
        }
        assignmentRepository.delete(a);
        return true;
    }

    private void validateQuestions(List<BigInteger> questionIds) {
        if (questionIds == null || questionIds.isEmpty()) {
            throw new IllegalArgumentException("至少选择 1 道题目");
        }
        for (BigInteger qid : questionIds) {
            Question q = questionRepository.findById(qid)
                    .orElseThrow(() -> new IllegalArgumentException("题目不存在: " + qid));
            if (!"published".equals(q.getStatus())) {
                throw new IllegalArgumentException("只能选用已发布的题目: " + qid);
            }
        }
    }

    private boolean isValidTransition(String from, String to) {
        if (from == null || to == null) return false;
        return switch (from) {
            case "draft" -> "published".equals(to);
            case "published" -> "closed".equals(to);
            case "closed" -> "archived".equals(to);
            default -> false;
        };
    }

    private Map<String, Object> toMap(Assignment a) {
        Map<String, Object> m = new HashMap<>();
        m.put("id", a.getId());
        m.put("title", a.getTitle());
        m.put("description", a.getDescription());
        m.put("class_id", a.getClassId());
        m.put("teacher_id", a.getTeacherId());
        m.put("question_ids", a.getQuestionIds());
        m.put("status", a.getStatus());
        m.put("due_at", a.getDueAt() != null ? a.getDueAt().toString() : null);
        m.put("created_at", a.getCreatedAt() != null ? a.getCreatedAt().toString() : null);
        m.put("updated_at", a.getUpdatedAt() != null ? a.getUpdatedAt().toString() : null);
        classRoomRepository.findById(a.getClassId())
                .ifPresent(cls -> m.put("class_name", cls.getName()));
        return m;
    }
}
