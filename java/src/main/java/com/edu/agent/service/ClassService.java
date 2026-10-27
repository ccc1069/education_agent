package com.edu.agent.service;

import com.edu.agent.db.entity.ClassMember;
import com.edu.agent.db.entity.ClassRoom;
import com.edu.agent.db.entity.Learner;
import com.edu.agent.db.repository.ClassMemberRepository;
import com.edu.agent.db.repository.ClassRoomRepository;
import com.edu.agent.db.repository.LearnerRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigInteger;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * 班级服务 -- 对齐 Python services/class_service.py。
 * - 教师创建/归档班级(自动生成 8 位邀请码)
 * - 学生通过邀请码加入
 * - 成员管理
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ClassService {

    private final ClassRoomRepository classRoomRepository;
    private final ClassMemberRepository classMemberRepository;
    private final LearnerRepository learnerRepository;

    @Transactional
    public Map<String, Object> createClass(String name, BigInteger teacherId, String description) {
        ClassRoom cls = new ClassRoom();
        cls.setName(name);
        cls.setTeacherId(teacherId);
        cls.setDescription(description != null ? description : "");
        cls.setIsActive(true);
        cls = classRoomRepository.save(cls);
        return toSummaryMap(cls, 0);
    }

    @Transactional(readOnly = true)
    public List<Map<String, Object>> listTeacherClasses(BigInteger teacherId) {
        return classRoomRepository.findByTeacherId(teacherId).stream()
                .map(cls -> toSummaryMap(cls, classMemberRepository.countByClassId(cls.getId())))
                .toList();
    }

    @Transactional(readOnly = true)
    public List<Map<String, Object>> listAllClasses() {
        return classRoomRepository.findAll().stream()
                .map(cls -> toSummaryMap(cls, classMemberRepository.countByClassId(cls.getId())))
                .toList();
    }

    @Transactional(readOnly = true)
    public Map<String, Object> getClass(BigInteger classId) {
        return classRoomRepository.findById(classId)
                .map(cls -> toSummaryMap(cls, classMemberRepository.countByClassId(cls.getId())))
                .orElse(null);
    }

    @Transactional(readOnly = true)
    public ClassRoom getClassEntity(BigInteger classId) {
        return classRoomRepository.findById(classId).orElse(null);
    }

    @Transactional
    public Map<String, Object> addMemberByInviteCode(String inviteCode, BigInteger learnerId) {
        ClassRoom cls = classRoomRepository.findByInviteCode(inviteCode)
                .orElseThrow(() -> new IllegalArgumentException("邀请码无效"));
        if (!Boolean.TRUE.equals(cls.getIsActive())) {
            throw new IllegalArgumentException("班级已归档,无法加入");
        }
        Optional<ClassMember> existing = classMemberRepository.findByClassIdAndLearnerId(cls.getId(), learnerId);
        if (existing.isPresent()) {
            Map<String, Object> r = new HashMap<>();
            r.put("class_id", cls.getId());
            r.put("learner_id", learnerId);
            r.put("already_member", true);
            return r;
        }
        ClassMember m = new ClassMember();
        m.setClassId(cls.getId());
        m.setLearnerId(learnerId);
        classMemberRepository.save(m);
        Map<String, Object> r = new HashMap<>();
        r.put("class_id", cls.getId());
        r.put("learner_id", learnerId);
        r.put("already_member", false);
        return r;
    }

    @Transactional(readOnly = true)
    public List<Map<String, Object>> listMembers(BigInteger classId) {
        List<ClassMember> members = classMemberRepository.findByClassId(classId);
        return members.stream().map(m -> {
            Map<String, Object> r = new HashMap<>();
            r.put("learner_id", m.getLearnerId());
            Optional<Learner> l = learnerRepository.findById(m.getLearnerId());
            r.put("public_id", l.map(Learner::getPublicId).orElse(null));
            r.put("name", l.map(Learner::getName).orElse(null));
            r.put("joined_at", m.getJoinedAt() != null ? m.getJoinedAt().toString() : null);
            return r;
        }).toList();
    }

    @Transactional
    public boolean removeMember(BigInteger classId, BigInteger learnerId) {
        return classMemberRepository.findByClassIdAndLearnerId(classId, learnerId)
                .map(m -> { classMemberRepository.delete(m); return true; })
                .orElse(false);
    }

    @Transactional
    public boolean archiveClass(BigInteger classId) {
        return classRoomRepository.findById(classId).map(cls -> {
            cls.setIsActive(false);
            classRoomRepository.save(cls);
            return true;
        }).orElse(false);
    }

    private Map<String, Object> toSummaryMap(ClassRoom cls, long memberCount) {
        Map<String, Object> m = new HashMap<>();
        m.put("id", cls.getId());
        m.put("name", cls.getName());
        m.put("description", cls.getDescription());
        m.put("teacher_id", cls.getTeacherId());
        m.put("invite_code", cls.getInviteCode());
        m.put("is_active", cls.getIsActive());
        m.put("member_count", memberCount);
        m.put("created_at", cls.getCreatedAt() != null ? cls.getCreatedAt().toString() : null);
        m.put("updated_at", cls.getUpdatedAt() != null ? cls.getUpdatedAt().toString() : null);
        return m;
    }
}
