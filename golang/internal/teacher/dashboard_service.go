package teacher

import (
	"sync"
)

// WeakPoint 薄弱知识点
type WeakPoint struct {
	KnowledgeID string  `json:"knowledge_id"`
	AvgMastery  float64 `json:"avg_mastery"`
	StudentCount int    `json:"student_count"`
}

// Intervention 干预建议
type Intervention struct {
	Type        string `json:"type"`
	Target      string `json:"target"`
	Description string `json:"description"`
	Priority    int    `json:"priority"`
}

// DashboardData 教师仪表盘数据
type DashboardData struct {
	ClassID       string        `json:"class_id"`
	AvgMastery    float64       `json:"avg_mastery"`
	WeakKnowledge []WeakPoint   `json:"weak_knowledge"`
	Interventions []Intervention `json:"interventions"`
	TotalStudents int           `json:"total_students"`
	TotalAssignments int        `json:"total_assignments"`
}

// DashboardService 仪表盘服务
type DashboardService struct {
	mu           sync.RWMutex
	classService *ClassService
	assignmentService *AssignmentService
}

// NewDashboardService 创建仪表盘服务
func NewDashboardService(classService *ClassService, assignmentService *AssignmentService) *DashboardService {
	return &DashboardService{
		classService: classService,
		assignmentService: assignmentService,
	}
}

// GetDashboard 获取班级仪表盘
func (s *DashboardService) GetDashboard(classID string) *DashboardData {
	class, err := s.classService.GetClass(classID)
	if err != nil {
		return &DashboardData{ClassID: classID}
	}

	assignments := s.assignmentService.ListByClass(classID)

	// 构造仪表盘数据
	dashboard := &DashboardData{
		ClassID:          classID,
		TotalStudents:    len(class.Members),
		TotalAssignments: len(assignments),
		AvgMastery:       0.75, // 模拟数据
		WeakKnowledge: []WeakPoint{
			{KnowledgeID: "algebra-basics", AvgMastery: 0.45, StudentCount: len(class.Members)},
		},
		Interventions: []Intervention{
			{Type: "review", Target: "algebra-basics", Description: "建议复习代数基础", Priority: 1},
		},
	}

	return dashboard
}
