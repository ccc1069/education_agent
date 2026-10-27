package auth

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"
)

// Key JWT 签名密钥类型
type Key []byte

// Claims JWT 声明
//
// 面试要点:
// - 纯标准库实现 HMAC-SHA256 JWT,无第三方依赖
// - Access token 30min, Refresh token 7 days
// - jti 用于令牌撤销
type Claims struct {
	UserID    string    `json:"sub"`
	Email     string    `json:"email"`
	Role      string    `json:"role"`
	TenantID  string    `json:"tenant_id"`
	LearnerID string    `json:"learner_id,omitempty"`
	TokenType string    `json:"type"` // "access" / "refresh"
	ExpiresAt time.Time `json:"exp"`
	IssuedAt  time.Time `json:"iat"`
	ID        string    `json:"jti"` // UUID for revocation
}

// 常用错误
var (
	ErrInvalidToken  = errors.New("invalid token")
	ErrTokenExpired  = errors.New("token expired")
	ErrInvalidFormat = errors.New("invalid token format")
	ErrInvalidSign   = errors.New("invalid signature")
)

// DefaultAccessDuration 默认 access token 有效期
const DefaultAccessDuration = 30 * time.Minute

// DefaultRefreshDuration 默认 refresh token 有效期
const DefaultRefreshDuration = 7 * 24 * time.Hour

// CreateToken 创建 JWT token (HS256)
//
// 格式: base64url(header).base64url(payload).base64url(signature)
// Signature = HMAC-SHA256(header.payload, secret)
func CreateToken(secret Key, claims Claims) (string, error) {
	// 构造 header
	header := map[string]string{
		"alg": "HS256",
		"typ": "JWT",
	}
	headerJSON, err := json.Marshal(header)
	if err != nil {
		return "", fmt.Errorf("marshal header: %w", err)
	}
	headerB64 := base64.RawURLEncoding.EncodeToString(headerJSON)

	// 构造 payload
	if claims.ID == "" {
		claims.ID = generateID()
	}
	if claims.IssuedAt.IsZero() {
		claims.IssuedAt = time.Now()
	}
	payloadJSON, err := json.Marshal(claims)
	if err != nil {
		return "", fmt.Errorf("marshal payload: %w", err)
	}
	payloadB64 := base64.RawURLEncoding.EncodeToString(payloadJSON)

	// 签名
	signingInput := headerB64 + "." + payloadB64
	sign := hmacSHA256(signingInput, secret)

	return signingInput + "." + sign, nil
}

// ParseToken 验证并解析 JWT token
func ParseToken(secret Key, tokenString string) (*Claims, error) {
	parts := strings.Split(tokenString, ".")
	if len(parts) != 3 {
		return nil, ErrInvalidFormat
	}

	// 验证签名
	signingInput := parts[0] + "." + parts[1]
	expectedSign := hmacSHA256(signingInput, secret)
	if !hmac.Equal([]byte(parts[2]), []byte(expectedSign)) {
		return nil, ErrInvalidSign
	}

	// 解析 payload
	payloadJSON, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return nil, fmt.Errorf("%w: decode payload: %v", ErrInvalidToken, err)
	}

	var claims Claims
	if err := json.Unmarshal(payloadJSON, &claims); err != nil {
		return nil, fmt.Errorf("%w: unmarshal payload: %v", ErrInvalidToken, err)
	}

	// 检查过期
	if !claims.ExpiresAt.IsZero() && time.Now().After(claims.ExpiresAt) {
		return nil, ErrTokenExpired
	}

	return &claims, nil
}

// CreateAccessToken 创建 access token（learnerID 写入 claims，供教学主链从 JWT 推断）
func CreateAccessToken(secret Key, userID, email, role, tenantID, learnerID string) (string, error) {
	claims := Claims{
		UserID:    userID,
		Email:     email,
		Role:      role,
		TenantID:  tenantID,
		LearnerID: learnerID,
		TokenType: "access",
		ExpiresAt: time.Now().Add(DefaultAccessDuration),
		IssuedAt:  time.Now(),
	}
	return CreateToken(secret, claims)
}

// CreateRefreshToken 创建 refresh token
func CreateRefreshToken(secret Key, userID, tenantID string) (string, error) {
	claims := Claims{
		UserID:    userID,
		TenantID:  tenantID,
		TokenType: "refresh",
		ExpiresAt: time.Now().Add(DefaultRefreshDuration),
		IssuedAt:  time.Now(),
	}
	return CreateToken(secret, claims)
}

// hmacSHA256 计算 HMAC-SHA256 并返回 base64url 编码
func hmacSHA256(input string, secret Key) string {
	h := hmac.New(sha256.New, secret)
	h.Write([]byte(input))
	return base64.RawURLEncoding.EncodeToString(h.Sum(nil))
}

// generateID 生成随机 ID (用于 jti)
func generateID() string {
	b := make([]byte, 16)
	rand.Read(b)
	return fmt.Sprintf("%x", b)
}
