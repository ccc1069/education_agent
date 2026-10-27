package privacy

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"encoding/base64"
	"errors"
	"io"
)

// EncryptPII 使用 AES-256-GCM 加密 PII 数据
//
// 格式: base64(iv || ciphertext || tag)
// IV 为 12 字节随机值,GCM tag 自动附加在密文末尾
//
// 面试要点:
// - AES-GCM 提供认证加密,同时保证机密性和完整性
// - 每次加密使用随机 IV,相同明文产生不同密文
func EncryptPII(plaintext string, key []byte) (string, error) {
	if len(key) != 32 {
		return "", errors.New("key must be 32 bytes for AES-256")
	}

	block, err := aes.NewCipher(key)
	if err != nil {
		return "", err
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}

	// 随机 IV
	iv := make([]byte, gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, iv); err != nil {
		return "", err
	}

	// Seal 自动附加 tag
	ciphertext := gcm.Seal(iv, iv, []byte(plaintext), nil)
	return base64.StdEncoding.EncodeToString(ciphertext), nil
}

// DecryptPII 解密 AES-256-GCM 加密的 PII 数据
func DecryptPII(ciphertext string, key []byte) (string, error) {
	if len(key) != 32 {
		return "", errors.New("key must be 32 bytes for AES-256")
	}

	data, err := base64.StdEncoding.DecodeString(ciphertext)
	if err != nil {
		return "", err
	}

	block, err := aes.NewCipher(key)
	if err != nil {
		return "", err
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}

	nonceSize := gcm.NonceSize()
	if len(data) < nonceSize {
		return "", errors.New("ciphertext too short")
	}

	iv, encrypted := data[:nonceSize], data[nonceSize:]
	plaintext, err := gcm.Open(nil, iv, encrypted, nil)
	if err != nil {
		return "", err
	}

	return string(plaintext), nil
}

// GenerateKey 生成随机 32 字节密钥
func GenerateKey() []byte {
	key := make([]byte, 32)
	rand.Read(key)
	return key
}
