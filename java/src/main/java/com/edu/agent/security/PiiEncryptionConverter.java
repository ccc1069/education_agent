package com.edu.agent.security;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

/**
 * JPA AttributeConverter -- 自动加解密 PII 字段。
 *
 * <p>使用方式:
 * <pre>{@code
 * @Convert(converter = PiiEncryptionConverter.class)
 * private String email;
 * }</pre>
 *
 * <p>面试要点:
 * <ul>
 *   <li>对应用层透明,数据库中存储密文</li>
 *   <li>查询时需注意: 加密字段无法直接做 WHERE 条件 (需额外哈希列)</li>
 * </ul>
 */
@Converter
@Component
public class PiiEncryptionConverter implements AttributeConverter<String, String> {

    private static PiiEncryption piiEncryption;

    @Autowired
    public void setPiiEncryption(PiiEncryption encryption) {
        PiiEncryptionConverter.piiEncryption = encryption;
    }

    /**
     * 写入数据库时加密
     */
    @Override
    public String convertToDatabaseColumn(String attribute) {
        if (attribute == null || piiEncryption == null) return attribute;
        return piiEncryption.encrypt(attribute);
    }

    /**
     * 从数据库读取时解密
     */
    @Override
    public String convertToEntityAttribute(String dbData) {
        if (dbData == null || piiEncryption == null) return dbData;
        return piiEncryption.decrypt(dbData);
    }
}
