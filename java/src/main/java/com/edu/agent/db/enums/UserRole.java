package com.edu.agent.db.enums;

/**
 * 用户角色枚举 -- 对齐 Python UserRole。
 * 持久化 value(如 "admin")而非 name()。
 */
public enum UserRole {
    STUDENT,
    TEACHER,
    ADMIN,
    PARENT,
    AUDITOR;

    public String value() {
        return name().toLowerCase();
    }

    public static UserRole fromValue(String v) {
        if (v == null) return STUDENT;
        return UserRole.valueOf(v.toUpperCase());
    }
}
