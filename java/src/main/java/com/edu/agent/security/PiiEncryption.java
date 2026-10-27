package com.edu.agent.security;

import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;

/**
 * PII 静态加密 (AES-256-GCM) -- 对齐 Go privacy/crypto.go。
 *
 * <p>面试要点:
 * <ul>
 *   <li>AES-GCM 提供认证加密,同时保证机密性和完整性</li>
 *   <li>每次加密使用随机 IV (12 字节),相同明文产生不同密文</li>
 *   <li>格式: Base64(IV || ciphertext || tag)</li>
 *   <li>密钥从 APP_PII_KEY 环境变量加载 (32 字节 hex),不存在则生成</li>
 * </ul>
 */
@Component
public class PiiEncryption {

    private static final Logger log = LoggerFactory.getLogger(PiiEncryption.class);

    private static final String ALGORITHM = "AES";
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int GCM_TAG_LENGTH = 128; // bits
    private static final int GCM_IV_LENGTH = 12;   // bytes
    private static final int KEY_LENGTH = 32;      // bytes (AES-256)

    private static final String ENV_PII_KEY = "APP_PII_KEY";

    private SecretKeySpec secretKey;
    private final SecureRandom secureRandom = new SecureRandom();

    /**
     * 初始化: 从环境变量加载密钥,不存在则生成并提示
     */
    @PostConstruct
    public void init() {
        String keyHex = System.getenv(ENV_PII_KEY);
        if (keyHex != null && !keyHex.isBlank()) {
            byte[] keyBytes = hexToBytes(keyHex);
            if (keyBytes.length != KEY_LENGTH) {
                throw new IllegalStateException(
                        "APP_PII_KEY must be " + (KEY_LENGTH * 2) + " hex chars (got " + keyBytes.length * 2 + ")");
            }
            this.secretKey = new SecretKeySpec(keyBytes, ALGORITHM);
            log.info("[PiiEncryption] Loaded key from environment");
        } else {
            // 生成随机密钥 (仅开发环境)
            byte[] keyBytes = new byte[KEY_LENGTH];
            secureRandom.nextBytes(keyBytes);
            this.secretKey = new SecretKeySpec(keyBytes, ALGORITHM);
            log.warn("[PiiEncryption] Generated random key (set APP_PII_KEY for persistence)");
        }
    }

    /**
     * 加密 PII 数据
     *
     * @param plaintext 明文
     * @return Base64(IV || ciphertext || tag)
     */
    public String encrypt(String plaintext) {
        if (plaintext == null) return null;
        try {
            byte[] iv = new byte[GCM_IV_LENGTH];
            secureRandom.nextBytes(iv);

            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            GCMParameterSpec parameterSpec = new GCMParameterSpec(GCM_TAG_LENGTH, iv);
            cipher.init(Cipher.ENCRYPT_MODE, secretKey, parameterSpec);

            byte[] ciphertext = cipher.doFinal(plaintext.getBytes(StandardCharsets.UTF_8));

            // 拼接 IV + ciphertext (tag 已附加)
            byte[] result = new byte[iv.length + ciphertext.length];
            System.arraycopy(iv, 0, result, 0, iv.length);
            System.arraycopy(ciphertext, 0, result, iv.length, ciphertext.length);

            return Base64.getEncoder().encodeToString(result);
        } catch (Exception e) {
            throw new PiiEncryptionException("Encryption failed", e);
        }
    }

    /**
     * 解密 PII 数据
     *
     * @param ciphertext Base64(IV || ciphertext || tag)
     * @return 明文
     */
    public String decrypt(String ciphertext) {
        if (ciphertext == null) return null;
        try {
            byte[] data = Base64.getDecoder().decode(ciphertext);

            if (data.length < GCM_IV_LENGTH) {
                throw new PiiEncryptionException("Ciphertext too short");
            }

            byte[] iv = Arrays.copyOfRange(data, 0, GCM_IV_LENGTH);
            byte[] encrypted = Arrays.copyOfRange(data, GCM_IV_LENGTH, data.length);

            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            GCMParameterSpec parameterSpec = new GCMParameterSpec(GCM_TAG_LENGTH, iv);
            cipher.init(Cipher.DECRYPT_MODE, secretKey, parameterSpec);

            byte[] plaintext = cipher.doFinal(encrypted);
            return new String(plaintext, StandardCharsets.UTF_8);
        } catch (PiiEncryptionException e) {
            throw e;
        } catch (Exception e) {
            throw new PiiEncryptionException("Decryption failed (tampered data?)", e);
        }
    }

    /**
     * hex 字符串转字节数组
     */
    private static byte[] hexToBytes(String hex) {
        int len = hex.length();
        byte[] data = new byte[len / 2];
        for (int i = 0; i < len; i += 2) {
            data[i / 2] = (byte) ((Character.digit(hex.charAt(i), 16) << 4)
                    + Character.digit(hex.charAt(i + 1), 16));
        }
        return data;
    }

    /**
     * PII 加密异常
     */
    public static class PiiEncryptionException extends RuntimeException {
        public PiiEncryptionException(String message) {
            super(message);
        }
        public PiiEncryptionException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
