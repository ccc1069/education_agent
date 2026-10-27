package com.edu.agent.security;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Field;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * PII 加密 round-trip 测试 -- 对齐 Go privacy/crypto.go。
 */
class PiiEncryptionTest {

    private PiiEncryption piiEncryption;

    @BeforeEach
    void setUp() throws Exception {
        piiEncryption = new PiiEncryption();
        // 使用反射调用 @PostConstruct 初始化
        piiEncryption.init();
    }

    @Test
    void encryptDecryptRoundTrip() {
        String plaintext = "user@example.com";
        String encrypted = piiEncryption.encrypt(plaintext);
        String decrypted = piiEncryption.decrypt(encrypted);

        assertThat(decrypted).isEqualTo(plaintext);
    }

    @Test
    void encryptProducesDifferentCiphertexts() {
        // 相同明文应产生不同密文 (随机 IV)
        String plaintext = "sensitive-data";
        String encrypted1 = piiEncryption.encrypt(plaintext);
        String encrypted2 = piiEncryption.encrypt(plaintext);

        assertThat(encrypted1).isNotEqualTo(encrypted2);
    }

    @Test
    void encryptNullReturnsNull() {
        assertThat(piiEncryption.encrypt(null)).isNull();
    }

    @Test
    void decryptNullReturnsNull() {
        assertThat(piiEncryption.decrypt(null)).isNull();
    }

    @Test
    void decryptTamperedDataFails() {
        String plaintext = "test-data";
        String encrypted = piiEncryption.encrypt(plaintext);

        // 篡改密文
        char[] chars = encrypted.toCharArray();
        chars[0] = chars[0] == 'A' ? 'B' : 'A';
        String tampered = new String(chars);

        assertThatThrownBy(() -> piiEncryption.decrypt(tampered))
                .isInstanceOf(PiiEncryption.PiiEncryptionException.class);
    }

    @Test
    void encryptChineseText() {
        String plaintext = "张三@example.com";
        String encrypted = piiEncryption.encrypt(plaintext);
        String decrypted = piiEncryption.decrypt(encrypted);

        assertThat(decrypted).isEqualTo(plaintext);
    }

    @Test
    void encryptLongText() {
        String plaintext = "a".repeat(10000);
        String encrypted = piiEncryption.encrypt(plaintext);
        String decrypted = piiEncryption.decrypt(encrypted);

        assertThat(decrypted).isEqualTo(plaintext);
    }

    @Test
    void encryptEmptyString() {
        String plaintext = "";
        String encrypted = piiEncryption.encrypt(plaintext);
        String decrypted = piiEncryption.decrypt(encrypted);

        assertThat(decrypted).isEqualTo(plaintext);
    }

    @Test
    void decryptTooShortDataFails() {
        // Base64 编码的过短数据
        String tooShort = "AQ=="; // 解码后仅 1 字节

        assertThatThrownBy(() -> piiEncryption.decrypt(tooShort))
                .isInstanceOf(PiiEncryption.PiiEncryptionException.class);
    }

    @Test
    void encryptedOutputIsBase64() {
        String plaintext = "test";
        String encrypted = piiEncryption.encrypt(plaintext);

        // 验证是有效 Base64
        assertThat(encrypted).matches("^[A-Za-z0-9+/]+=*$");
    }

    @Test
    void encryptedOutputContainsIV() {
        String plaintext = "test";
        String encrypted = piiEncryption.encrypt(plaintext);

        // 解密后应能还原,证明 IV 被正确嵌入
        String decrypted = piiEncryption.decrypt(encrypted);
        assertThat(decrypted).isEqualTo(plaintext);
    }
}
