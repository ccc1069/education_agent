package auth

import (
	"golang.org/x/crypto/bcrypt"
)

// DefaultCost bcrypt 默认 cost (12)
const DefaultCost = 12

// HashPassword 使用 bcrypt 哈希密码
//
// 面试要点:
// - bcrypt 自动加盐,每次结果不同
// - cost=12 是安全与性能的平衡点
// - 使用 golang.org/x/crypto/bcrypt (唯一外部依赖)
func HashPassword(password string) (string, error) {
	hash, err := bcrypt.GenerateFromPassword([]byte(password), DefaultCost)
	if err != nil {
		return "", err
	}
	return string(hash), nil
}

// VerifyPassword 验证密码与哈希是否匹配 (constant-time)
func VerifyPassword(hash, password string) bool {
	err := bcrypt.CompareHashAndPassword([]byte(hash), []byte(password))
	return err == nil
}
