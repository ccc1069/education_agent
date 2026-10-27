package com.edu.agent.audit;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * 标记需要写入审计日志的方法。
 * 由 AuditAspect 拦截,在方法成功返回后写入一条 audit_logs 记录(HMAC 链)。
 *
 * 用法:
 *   @Auditable(action = "class.create", target = "class:#{#result.id}")
 *   public Map<String, Object> createClass(...) { ... }
 *
 * SpEL 支持:
 *   #actor / #target / #metadata 表达式,引用方法参数(#argName)或返回值(#result)
 *   默认 actor 取当前认证用户 email,target 取 "#target" 参数,metadata 为空
 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface Auditable {

    /** 动作类型,如 class.create / assignment.publish / user.login。 */
    String action();

    /** 目标标识 SpEL,如 "class:#{#result.id}" 或 "user:#{#req.email}"。默认空。 */
    String target() default "";

    /**
     * 元数据 SpEL,JSON 形式或 SpEL map。
     * 例: "{ 'name': #req.name }" 或 "#result"。
     */
    String metadata() default "";

    /** 是否记录失败(默认仅记录成功)。 */
    boolean recordOnFailure() default false;
}
