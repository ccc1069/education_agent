package teacher

import (
	"crypto/rand"
	"fmt"
	"sync"
	"time"
)

// Class 班级
type Class struct {
	ID         string    `json:"id"`
	Name       string    `json:"name"`
	TenantID   string    `json:"tenant_id"`
	TeacherID  string    `json:"teacher_id"`
	InviteCode string    `json:"invite_code"`
	Members    []string  `json:"members"` // learner IDs
	CreatedAt  time.Time `json:"created_at"`
}

// ClassService 班级管理服务
type ClassService struct {
	mu       sync.RWMutex
	classes  map[string]*Class
	byCode   map[string]string // inviteCode -> classID
	onSave   func(*Class) error
	onDelete func(id string) error
}

// NewClassService 创建班级服务
func NewClassService() *ClassService {
	return &ClassService{
		classes: make(map[string]*Class),
		byCode:  make(map[string]string),
	}
}

// SetPersistHooks 设置落盘钩子
func (s *ClassService) SetPersistHooks(onSave func(*Class) error, onDelete func(id string) error) {
	s.onSave = onSave
	s.onDelete = onDelete
}

// Import 启动加载，不触发落盘
func (s *ClassService) Import(class *Class) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.classes[class.ID] = class
	s.byCode[class.InviteCode] = class.ID
}

func (s *ClassService) persistLocked(class *Class) {
	if s.onSave != nil && class != nil {
		_ = s.onSave(class)
	}
}

// CreateClass 创建班级 (8 位邀请码)
func (s *ClassService) CreateClass(name, teacherID, tenantID string) (*Class, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	class := &Class{
		ID:         generateID(),
		Name:       name,
		TenantID:   tenantID,
		TeacherID:  teacherID,
		InviteCode: generateInviteCode(),
		Members:    []string{},
		CreatedAt:  time.Now(),
	}

	s.classes[class.ID] = class
	s.byCode[class.InviteCode] = class.ID
	s.persistLocked(class)

	return class, nil
}

// JoinClass 通过邀请码加入班级
func (s *ClassService) JoinClass(inviteCode, learnerID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	classID, ok := s.byCode[inviteCode]
	if !ok {
		return fmt.Errorf("invalid invite code: %s", inviteCode)
	}

	class := s.classes[classID]
	// 检查是否已在班级中
	for _, m := range class.Members {
		if m == learnerID {
			return nil // 已在班级中
		}
	}

	class.Members = append(class.Members, learnerID)
	s.persistLocked(class)
	return nil
}

// GetClass 获取班级
func (s *ClassService) GetClass(classID string) (*Class, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	class, ok := s.classes[classID]
	if !ok {
		return nil, fmt.Errorf("class not found: %s", classID)
	}
	return class, nil
}

// ListByTeacher 列出教师的班级
func (s *ClassService) ListByTeacher(teacherID string) []*Class {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var result []*Class
	for _, class := range s.classes {
		if class.TeacherID == teacherID {
			result = append(result, class)
		}
	}
	return result
}

// ListByStudent 列出学生加入的班级
func (s *ClassService) ListByStudent(learnerID string) []*Class {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var result []*Class
	for _, class := range s.classes {
		for _, m := range class.Members {
			if m == learnerID {
				result = append(result, class)
				break
			}
		}
	}
	return result
}

// ArchiveClass 归档班级
func (s *ClassService) ArchiveClass(classID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	class, ok := s.classes[classID]
	if !ok {
		return fmt.Errorf("class not found: %s", classID)
	}
	class.Name = class.Name + " (已归档)"
	s.persistLocked(class)
	return nil
}

// RemoveMember 移除班级成员
func (s *ClassService) RemoveMember(classID, learnerID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	class, ok := s.classes[classID]
	if !ok {
		return fmt.Errorf("class not found: %s", classID)
	}

	for i, m := range class.Members {
		if m == learnerID {
			class.Members = append(class.Members[:i], class.Members[i+1:]...)
			s.persistLocked(class)
			return nil
		}
	}
	return fmt.Errorf("member not found in class")
}

// generateInviteCode 生成 8 位邀请码
func generateInviteCode() string {
	const charset = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789" // 去除易混淆字符
	b := make([]byte, 8)
	rand.Read(b)
	for i := range b {
		b[i] = charset[b[i]%byte(len(charset))]
	}
	return string(b)
}

// generateID 生成随机 ID
func generateID() string {
	b := make([]byte, 12)
	rand.Read(b)
	return fmt.Sprintf("cls-%x", b)
}
