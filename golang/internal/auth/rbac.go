package auth

// Role 角色类型
type Role string

const (
	RoleStudent  Role = "student"
	RoleTeacher  Role = "teacher"
	RoleAdmin    Role = "admin"
	RoleParent   Role = "parent"
	RoleAuditor  Role = "auditor"
)

// roleHierarchy 角色层级 (数值越大权限越高)
var roleHierarchy = map[Role]int{
	RoleStudent: 1,
	RoleParent:  2,
	RoleTeacher: 3,
	RoleAuditor: 4,
	RoleAdmin:   5,
}

// CurrentUser 当前认证用户
//
// 面试要点:
// - 通过 HTTP 中间件注入 context
// - LearnerID 可选 (student 角色关联)
type CurrentUser struct {
	ID        string
	Email     string
	Role      Role
	TenantID  string
	LearnerID string // optional, for student role
}

// HasRole 检查用户是否属于指定角色之一
func HasRole(user *CurrentUser, roles ...Role) bool {
	if user == nil {
		return false
	}
	for _, r := range roles {
		if user.Role == r {
			return true
		}
	}
	return false
}

// HasMinRole 检查用户是否达到最低角色层级
//
// 层级: admin(5) > auditor(4) > teacher(3) > parent(2) > student(1)
func HasMinRole(user *CurrentUser, minRole Role) bool {
	if user == nil {
		return false
	}
	userLevel, ok := roleHierarchy[user.Role]
	if !ok {
		return false
	}
	minLevel, ok := roleHierarchy[minRole]
	if !ok {
		return false
	}
	return userLevel >= minLevel
}

// IsAdmin 是否为管理员
func IsAdmin(user *CurrentUser) bool {
	return HasRole(user, RoleAdmin)
}

// IsTeacherOrAbove 是否为教师或更高权限
func IsTeacherOrAbove(user *CurrentUser) bool {
	return HasMinRole(user, RoleTeacher)
}

// GetRoleLevel 获取角色层级数值
func GetRoleLevel(role Role) int {
	if level, ok := roleHierarchy[role]; ok {
		return level
	}
	return 0
}
