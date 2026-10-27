package privacy

import "strings"

// MaskEmail 邮箱脱敏: a***@domain.com
//
// 保留首字符和 @ 及后续域名
func MaskEmail(email string) string {
	at := strings.Index(email, "@")
	if at <= 1 {
		return email
	}
	return email[:1] + "***" + email[at:]
}

// MaskPhone 手机号脱敏: 138****1234
//
// 保留前 3 位和后 4 位
func MaskPhone(phone string) string {
	if len(phone) < 7 {
		return phone
	}
	return phone[:3] + "****" + phone[len(phone)-4:]
}

// MaskIDCard 身份证脱敏: 110***********1234
//
// 保留前 3 位和后 4 位
func MaskIDCard(id string) string {
	if len(id) < 7 {
		return id
	}
	return id[:3] + strings.Repeat("*", len(id)-7) + id[len(id)-4:]
}

// MaskName 姓名脱敏: 张**
//
// 保留首字符,其余替换为 *
func MaskName(name string) string {
	runes := []rune(name)
	if len(runes) <= 1 {
		return name
	}
	return string(runes[:1]) + strings.Repeat("*", len(runes)-1)
}

// MaskGeneric 通用脱敏: 保留前 2 后 2
func MaskGeneric(s string) string {
	if len(s) <= 4 {
		return s
	}
	return s[:2] + strings.Repeat("*", len(s)-4) + s[len(s)-2:]
}
