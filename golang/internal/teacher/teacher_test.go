package teacher

import (
	"testing"
	"time"
)

func TestClassService_CreateClass(t *testing.T) {
	service := NewClassService()

	class, err := service.CreateClass("七年级一班", "teacher-001", "tenant-001")
	if err != nil {
		t.Fatalf("CreateClass failed: %v", err)
	}
	if class.Name != "七年级一班" {
		t.Errorf("name: got %s, want 七年级一班", class.Name)
	}
	if class.InviteCode == "" {
		t.Error("invite code should not be empty")
	}
	if len(class.InviteCode) != 8 {
		t.Errorf("invite code length: got %d, want 8", len(class.InviteCode))
	}
}

func TestClassService_JoinClass(t *testing.T) {
	service := NewClassService()

	class, _ := service.CreateClass("七年级一班", "teacher-001", "tenant-001")

	// 学生加入
	err := service.JoinClass(class.InviteCode, "student-001")
	if err != nil {
		t.Fatalf("JoinClass failed: %v", err)
	}

	// 验证成员
	class, _ = service.GetClass(class.ID)
	if len(class.Members) != 1 {
		t.Errorf("members: got %d, want 1", len(class.Members))
	}

	// 重复加入 (幂等)
	err = service.JoinClass(class.InviteCode, "student-001")
	if err != nil {
		t.Errorf("duplicate join should not error: %v", err)
	}
	if len(class.Members) != 1 {
		t.Errorf("members should still be 1 after duplicate join")
	}

	// 无效邀请码
	err = service.JoinClass("INVALID", "student-002")
	if err == nil {
		t.Error("should fail with invalid invite code")
	}
}

func TestClassService_ListByTeacher(t *testing.T) {
	service := NewClassService()

	service.CreateClass("班级1", "teacher-001", "tenant-001")
	service.CreateClass("班级2", "teacher-001", "tenant-001")
	service.CreateClass("班级3", "teacher-002", "tenant-001")

	classes := service.ListByTeacher("teacher-001")
	if len(classes) != 2 {
		t.Errorf("teacher-001 classes: got %d, want 2", len(classes))
	}
}

func TestClassService_ListByStudent(t *testing.T) {
	service := NewClassService()

	class1, _ := service.CreateClass("班级1", "teacher-001", "tenant-001")
	class2, _ := service.CreateClass("班级2", "teacher-002", "tenant-001")

	service.JoinClass(class1.InviteCode, "student-001")
	service.JoinClass(class2.InviteCode, "student-001")

	classes := service.ListByStudent("student-001")
	if len(classes) != 2 {
		t.Errorf("student-001 classes: got %d, want 2", len(classes))
	}
}

func TestAssignmentService_CreateAndUpdate(t *testing.T) {
	service := NewAssignmentService()

	dueDate := time.Now().Add(7 * 24 * time.Hour)
	a, err := service.CreateAssignment("class-001", "第一次作业", "完成第1-10题", []string{"q1", "q2"}, dueDate)
	if err != nil {
		t.Fatalf("CreateAssignment failed: %v", err)
	}
	if a.Status != AssignmentDraft {
		t.Errorf("status: got %s, want draft", a.Status)
	}

	// 发布
	err = service.UpdateStatus(a.ID, AssignmentPublished)
	if err != nil {
		t.Errorf("publish should succeed: %v", err)
	}

	// 关闭
	err = service.UpdateStatus(a.ID, AssignmentClosed)
	if err != nil {
		t.Errorf("close should succeed: %v", err)
	}
}

func TestAssignmentService_InvalidTransition(t *testing.T) {
	service := NewAssignmentService()

	a, _ := service.CreateAssignment("class-001", "作业", "描述", []string{}, time.Now())

	// draft -> closed (非法)
	err := service.UpdateStatus(a.ID, AssignmentClosed)
	if err == nil {
		t.Error("draft->closed should fail")
	}
}

func TestCanTransitionAssignment(t *testing.T) {
	tests := []struct {
		from, to AssignmentStatus
		want     bool
	}{
		{AssignmentDraft, AssignmentPublished, true},
		{AssignmentPublished, AssignmentClosed, true},
		{AssignmentClosed, AssignmentArchived, true},
		{AssignmentDraft, AssignmentClosed, false},
		{AssignmentArchived, AssignmentDraft, false},
	}
	for _, tt := range tests {
		got := CanTransitionAssignment(tt.from, tt.to)
		if got != tt.want {
			t.Errorf("CanTransitionAssignment(%s,%s) = %v, want %v", tt.from, tt.to, got, tt.want)
		}
	}
}

func TestDashboardService(t *testing.T) {
	classService := NewClassService()
	assignmentService := NewAssignmentService()
	dashboardService := NewDashboardService(classService, assignmentService)

	class, _ := classService.CreateClass("七年级一班", "teacher-001", "tenant-001")
	classService.JoinClass(class.InviteCode, "student-001")
	classService.JoinClass(class.InviteCode, "student-002")

	assignmentService.CreateAssignment(class.ID, "作业1", "描述", []string{"q1"}, time.Now())

	dashboard := dashboardService.GetDashboard(class.ID)
	if dashboard.TotalStudents != 2 {
		t.Errorf("total students: got %d, want 2", dashboard.TotalStudents)
	}
	if dashboard.TotalAssignments != 1 {
		t.Errorf("total assignments: got %d, want 1", dashboard.TotalAssignments)
	}
}
