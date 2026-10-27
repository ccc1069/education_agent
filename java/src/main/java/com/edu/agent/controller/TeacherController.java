package com.edu.agent.controller;

import com.edu.agent.audit.Auditable;
import com.edu.agent.db.entity.User;
import com.edu.agent.db.enums.UserRole;
import com.edu.agent.db.repository.UserRepository;
import com.edu.agent.security.PrincipalUser;
import com.edu.agent.security.SecurityContextHelper;
import com.edu.agent.service.AssignmentService;
import com.edu.agent.service.ClassService;
import com.edu.agent.service.TeacherDashboardService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.math.BigInteger;
import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * 教师后台路由 -- 对齐 Python /api/v1/teacher/*。
 * - 班级 CRUD + 邀请码加入 + 成员管理 + 归档
 * - 作业 CRUD + 状态迁移
 * - 班级学情看板
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/teacher")
@RequiredArgsConstructor
public class TeacherController {

    private final ClassService classService;
    private final AssignmentService assignmentService;
    private final TeacherDashboardService dashboardService;
    private final SecurityContextHelper securityContext;
    private final UserRepository userRepository;

    public record CreateClassRequest(@NotBlank @Size(max = 128) String name,
                                     @Size(max = 2000) String description) {}
    public record JoinClassRequest(@NotBlank @Size(max = 16) String invite_code) {}
    public record CreateAssignmentRequest(@NotBlank @Size(max = 256) String title,
                                          BigInteger class_id,
                                          List<BigInteger> question_ids,
                                          @Size(max = 2000) String description,
                                          String due_at) {}
    public record UpdateAssignmentRequest(@NotBlank @Size(max = 256) String title,
                                          @Size(max = 2000) String description,
                                          List<BigInteger> question_ids,
                                          String due_at,
                                          BigInteger class_id) {}
    public record UpdateAssignmentStatusRequest(@NotBlank String new_status) {}

    // ---------- 班级 ----------

    @PostMapping("/classes")
    @PreAuthorize("hasAnyRole('TEACHER','ADMIN')")
    @ResponseStatus(HttpStatus.CREATED)
    @Auditable(action = "class.create", target = "class:#{#result.id}", metadata = "{ 'name': #req.name }")
    public Map<String, Object> createClass(@Valid @RequestBody CreateClassRequest req) {
        PrincipalUser p = securityContext.require();
        return classService.createClass(req.name(), p.getId(), req.description());
    }

    @GetMapping("/classes")
    @PreAuthorize("hasAnyRole('TEACHER','ADMIN')")
    public List<Map<String, Object>> listMyClasses() {
        PrincipalUser p = securityContext.require();
        if (p.hasRole(UserRole.ADMIN)) return classService.listAllClasses();
        return classService.listTeacherClasses(p.getId());
    }

    @GetMapping("/classes/{classId}")
    @PreAuthorize("hasAnyRole('TEACHER','ADMIN')")
    public Map<String, Object> getClass(@PathVariable BigInteger classId) {
        PrincipalUser p = securityContext.require();
        Map<String, Object> cls = classService.getClass(classId);
        if (cls == null) throw new IllegalArgumentException("班级不存在");
        requireClassOwner(cls, p);
        List<Map<String, Object>> members = classService.listMembers(classId);
        cls.put("members", members);
        return cls;
    }

    @PostMapping("/classes/join")
    @PreAuthorize("hasRole('STUDENT')")
    public Map<String, Object> joinClass(@Valid @RequestBody JoinClassRequest req) {
        PrincipalUser p = securityContext.require();
        BigInteger learnerId = resolveLearnerId(p);
        return classService.addMemberByInviteCode(req.invite_code(), learnerId);
    }

    @GetMapping("/classes/{classId}/members")
    @PreAuthorize("hasAnyRole('TEACHER','ADMIN')")
    public List<Map<String, Object>> listMembers(@PathVariable BigInteger classId) {
        PrincipalUser p = securityContext.require();
        Map<String, Object> cls = classService.getClass(classId);
        if (cls == null) throw new IllegalArgumentException("班级不存在");
        requireClassOwner(cls, p);
        return classService.listMembers(classId);
    }

    @PostMapping("/classes/{classId}/members/{learnerId}/delete")
    @PreAuthorize("hasAnyRole('TEACHER','ADMIN')")
    public Map<String, Object> removeMember(@PathVariable BigInteger classId,
                                             @PathVariable BigInteger learnerId) {
        PrincipalUser p = securityContext.require();
        Map<String, Object> cls = classService.getClass(classId);
        if (cls == null) throw new IllegalArgumentException("班级不存在");
        requireClassOwner(cls, p);
        boolean ok = classService.removeMember(classId, learnerId);
        if (!ok) throw new IllegalArgumentException("成员不存在");
        return Map.of("success", true, "class_id", classId, "learner_id", learnerId);
    }

    @PostMapping("/classes/{classId}/archive")
    @PreAuthorize("hasAnyRole('TEACHER','ADMIN')")
    public Map<String, Object> archiveClass(@PathVariable BigInteger classId) {
        PrincipalUser p = securityContext.require();
        Map<String, Object> cls = classService.getClass(classId);
        if (cls == null) throw new IllegalArgumentException("班级不存在");
        requireClassOwner(cls, p);
        classService.archiveClass(classId);
        return Map.of("class_id", classId, "is_active", false);
    }

    @GetMapping("/classes/{classId}/dashboard")
    @PreAuthorize("hasAnyRole('TEACHER','ADMIN')")
    public Map<String, Object> getClassDashboard(@PathVariable BigInteger classId) {
        PrincipalUser p = securityContext.require();
        Map<String, Object> cls = classService.getClass(classId);
        if (cls == null) throw new IllegalArgumentException("班级不存在");
        requireClassOwner(cls, p);
        Map<String, Object> dashboard = dashboardService.getClassDashboard(classId);
        if (dashboard == null) throw new IllegalArgumentException("班级不存在");
        return dashboard;
    }

    // ---------- 作业 ----------

    @PostMapping("/assignments")
    @PreAuthorize("hasAnyRole('TEACHER','ADMIN')")
    @ResponseStatus(HttpStatus.CREATED)
    @Auditable(action = "assignment.create", target = "assignment:#{#result.id}",
               metadata = "{ 'title': #req.title, 'class_id': #req.class_id }")
    public Map<String, Object> createAssignment(@Valid @RequestBody CreateAssignmentRequest req) {
        PrincipalUser p = securityContext.require();
        if (req.class_id() == null) throw new IllegalArgumentException("class_id 不能为空");
        if (req.question_ids() == null || req.question_ids().isEmpty()) {
            throw new IllegalArgumentException("question_ids 至少 1 道");
        }
        Instant dueAt = req.due_at() != null && !req.due_at().isBlank() ? Instant.parse(req.due_at()) : null;
        return assignmentService.createAssignment(
                req.title(), req.class_id(), p.getId(), req.question_ids(),
                req.description(), dueAt, p.hasRole(UserRole.ADMIN));
    }

    @GetMapping("/assignments")
    @PreAuthorize("hasAnyRole('TEACHER','ADMIN')")
    public List<Map<String, Object>> listAssignments(@RequestParam(required = false) String status,
                                                      @RequestParam(required = false) BigInteger class_id) {
        PrincipalUser p = securityContext.require();
        if (class_id != null) {
            if (!p.hasRole(UserRole.ADMIN)) {
                Map<String, Object> cls = classService.getClass(class_id);
                requireClassOwner(cls, p);
            }
            return assignmentService.listClassAssignments(class_id, status);
        }
        if (p.hasRole(UserRole.ADMIN)) return assignmentService.listAllAssignments(status);
        return assignmentService.listTeacherAssignments(p.getId(), status);
    }

    @GetMapping("/assignments/mine")
    @PreAuthorize("hasRole('STUDENT')")
    public List<Map<String, Object>> listStudentAssignments() {
        PrincipalUser p = securityContext.require();
        BigInteger learnerId = resolveLearnerId(p);
        return assignmentService.listLearnerAssignments(learnerId);
    }

    @GetMapping("/assignments/{assignmentId}")
    @PreAuthorize("hasAnyRole('TEACHER','ADMIN')")
    public Map<String, Object> getAssignment(@PathVariable BigInteger assignmentId) {
        PrincipalUser p = securityContext.require();
        Map<String, Object> a = assignmentService.getAssignment(assignmentId);
        if (a == null) throw new IllegalArgumentException("作业不存在");
        if (!p.hasRole(UserRole.ADMIN) && !a.get("teacher_id").equals(p.getId())) {
            throw new AccessDeniedException("只能查看自己布置的作业");
        }
        return a;
    }

    @PostMapping("/assignments/{assignmentId}")
    @PreAuthorize("hasAnyRole('TEACHER','ADMIN')")
    public Map<String, Object> updateAssignment(@PathVariable BigInteger assignmentId,
                                                 @Valid @RequestBody UpdateAssignmentRequest req) {
        PrincipalUser p = securityContext.require();
        Map<String, Object> existing = assignmentService.getAssignment(assignmentId);
        if (existing == null) throw new IllegalArgumentException("作业不存在");
        if (!p.hasRole(UserRole.ADMIN) && !existing.get("teacher_id").equals(p.getId())) {
            throw new AccessDeniedException("只能编辑自己布置的作业");
        }
        Instant dueAt = req.due_at() != null && !req.due_at().isBlank() ? Instant.parse(req.due_at()) : null;
        return assignmentService.updateAssignment(
                assignmentId, req.title(), req.description(), req.question_ids(),
                dueAt, req.class_id(), p.hasRole(UserRole.ADMIN), p.getId());
    }

    @PostMapping("/assignments/{assignmentId}/status")
    @PreAuthorize("hasAnyRole('TEACHER','ADMIN')")
    public Map<String, Object> updateAssignmentStatus(@PathVariable BigInteger assignmentId,
                                                       @Valid @RequestBody UpdateAssignmentStatusRequest req) {
        PrincipalUser p = securityContext.require();
        Map<String, Object> existing = assignmentService.getAssignment(assignmentId);
        if (existing == null) throw new IllegalArgumentException("作业不存在");
        if (!p.hasRole(UserRole.ADMIN) && !existing.get("teacher_id").equals(p.getId())) {
            throw new AccessDeniedException("只能修改自己布置的作业状态");
        }
        Map<String, Object> result = assignmentService.updateStatus(assignmentId, req.new_status());
        if (result == null) throw new IllegalArgumentException("作业不存在");
        return result;
    }

    @PostMapping("/assignments/{assignmentId}/delete")
    @PreAuthorize("hasAnyRole('TEACHER','ADMIN')")
    @Auditable(action = "assignment.delete", target = "assignment:#{#assignmentId}")
    public Map<String, Object> deleteAssignment(@PathVariable BigInteger assignmentId) {
        PrincipalUser p = securityContext.require();
        Map<String, Object> existing = assignmentService.getAssignment(assignmentId);
        if (existing == null) throw new IllegalArgumentException("作业不存在");
        if (!p.hasRole(UserRole.ADMIN) && !existing.get("teacher_id").equals(p.getId())) {
            throw new AccessDeniedException("只能删除自己布置的作业");
        }
        boolean ok = assignmentService.deleteAssignment(assignmentId);
        if (!ok) throw new IllegalArgumentException("作业不存在");
        return Map.of("success", true, "id", assignmentId);
    }

    // ---------- helpers ----------

    private void requireClassOwner(Map<String, Object> cls, PrincipalUser p) {
        if (cls == null) throw new IllegalArgumentException("班级不存在");
        if (!p.hasRole(UserRole.ADMIN) && !cls.get("teacher_id").equals(p.getId())) {
            throw new AccessDeniedException("只能操作自己创建的班级");
        }
    }

    private BigInteger resolveLearnerId(PrincipalUser p) {
        User u = userRepository.findById(p.getId())
                .orElseThrow(() -> new IllegalStateException("用户不存在"));
        if (u.getLearnerId() == null) {
            throw new AccessDeniedException("当前用户未绑定 learner profile");
        }
        return u.getLearnerId();
    }
}
