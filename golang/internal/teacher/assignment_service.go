package teacher

import (
	"crypto/rand"
	"fmt"
	"sync"
	"time"
)

// AssignmentStatus 作业状态
type AssignmentStatus string

const (
	AssignmentDraft     AssignmentStatus = "draft"
	AssignmentPublished AssignmentStatus = "published"
	AssignmentClosed    AssignmentStatus = "closed"
	AssignmentArchived  AssignmentStatus = "archived"
)

// Assignment 作业
type Assignment struct {
	ID          string           `json:"id"`
	ClassID     string           `json:"class_id"`
	Title       string           `json:"title"`
	Description string           `json:"description"`
	QuestionIDs []string         `json:"question_ids"`
	Status      AssignmentStatus `json:"status"`
	DueDate     time.Time        `json:"due_date"`
	CreatedAt   time.Time        `json:"created_at"`
	UpdatedAt   time.Time        `json:"updated_at"`
}

// validAssignmentTransitions 作业状态转换
var validAssignmentTransitions = map[AssignmentStatus]map[AssignmentStatus]bool{
	AssignmentDraft:     {AssignmentPublished: true},
	AssignmentPublished: {AssignmentClosed: true},
	AssignmentClosed:    {AssignmentArchived: true},
	AssignmentArchived:  {},
}

// CanTransitionAssignment 检查作业状态转换
func CanTransitionAssignment(from, to AssignmentStatus) bool {
	if m, ok := validAssignmentTransitions[from]; ok {
		return m[to]
	}
	return false
}

// AssignmentService 作业服务
type AssignmentService struct {
	mu          sync.RWMutex
	assignments map[string]*Assignment
	onSave      func(*Assignment) error
	onDelete    func(id string) error
}

// NewAssignmentService 创建作业服务
func NewAssignmentService() *AssignmentService {
	return &AssignmentService{
		assignments: make(map[string]*Assignment),
	}
}

// SetPersistHooks 设置落盘钩子
func (s *AssignmentService) SetPersistHooks(onSave func(*Assignment) error, onDelete func(id string) error) {
	s.onSave = onSave
	s.onDelete = onDelete
}

// Import 启动加载
func (s *AssignmentService) Import(a *Assignment) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.assignments[a.ID] = a
}

func (s *AssignmentService) persistLocked(a *Assignment) {
	if s.onSave != nil && a != nil {
		_ = s.onSave(a)
	}
}

// CreateAssignment 创建作业
func (s *AssignmentService) CreateAssignment(classID, title, description string, questionIDs []string, dueDate time.Time) (*Assignment, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	assignment := &Assignment{
		ID:          generateAssignmentID(),
		ClassID:     classID,
		Title:       title,
		Description: description,
		QuestionIDs: questionIDs,
		Status:      AssignmentDraft,
		DueDate:     dueDate,
		CreatedAt:   time.Now(),
		UpdatedAt:   time.Now(),
	}

	s.assignments[assignment.ID] = assignment
	s.persistLocked(assignment)
	return assignment, nil
}

// UpdateStatus 更新作业状态
func (s *AssignmentService) UpdateStatus(id string, newStatus AssignmentStatus) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	a, ok := s.assignments[id]
	if !ok {
		return fmt.Errorf("assignment not found: %s", id)
	}

	if !CanTransitionAssignment(a.Status, newStatus) {
		return fmt.Errorf("invalid transition: %s -> %s", a.Status, newStatus)
	}

	a.Status = newStatus
	a.UpdatedAt = time.Now()
	s.persistLocked(a)
	return nil
}

// GetAssignment 获取作业
func (s *AssignmentService) GetAssignment(id string) (*Assignment, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	a, ok := s.assignments[id]
	if !ok {
		return nil, fmt.Errorf("assignment not found: %s", id)
	}
	return a, nil
}

// Update 更新作业
func (s *AssignmentService) Update(id, title, description string, questionIDs []string, dueDate time.Time) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	a, ok := s.assignments[id]
	if !ok {
		return fmt.Errorf("assignment not found: %s", id)
	}

	a.Title = title
	a.Description = description
	a.QuestionIDs = questionIDs
	a.DueDate = dueDate
	a.UpdatedAt = time.Now()
	s.persistLocked(a)
	return nil
}

// Delete 删除作业
func (s *AssignmentService) Delete(id string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if _, ok := s.assignments[id]; !ok {
		return fmt.Errorf("assignment not found: %s", id)
	}
	delete(s.assignments, id)
	if s.onDelete != nil {
		_ = s.onDelete(id)
	}
	return nil
}

// ListByTeacher 列出教师的所有作业 (通过班级关联)
func (s *AssignmentService) ListByTeacher(teacherID string, classes []*Class) []*Assignment {
	s.mu.RLock()
	defer s.mu.RUnlock()

	classIDs := make(map[string]bool)
	for _, c := range classes {
		if c.TeacherID == teacherID {
			classIDs[c.ID] = true
		}
	}

	var result []*Assignment
	for _, a := range s.assignments {
		if classIDs[a.ClassID] {
			result = append(result, a)
		}
	}
	return result
}

// ListByStudent 列出学生的作业 (通过班级成员关系)
func (s *AssignmentService) ListByStudent(learnerID string, classes []*Class) []*Assignment {
	s.mu.RLock()
	defer s.mu.RUnlock()

	classIDs := make(map[string]bool)
	for _, c := range classes {
		for _, m := range c.Members {
			if m == learnerID {
				classIDs[c.ID] = true
				break
			}
		}
	}

	var result []*Assignment
	for _, a := range s.assignments {
		if classIDs[a.ClassID] {
			result = append(result, a)
		}
	}
	return result
}

// ListByClass 列出班级作业
func (s *AssignmentService) ListByClass(classID string) []*Assignment {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var result []*Assignment
	for _, a := range s.assignments {
		if a.ClassID == classID {
			result = append(result, a)
		}
	}
	return result
}

// generateAssignmentID 生成作业 ID
func generateAssignmentID() string {
	b := make([]byte, 12)
	rand.Read(b)
	return fmt.Sprintf("asg-%x", b)
}
