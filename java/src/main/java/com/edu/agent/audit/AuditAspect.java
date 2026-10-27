package com.edu.agent.audit;

import com.edu.agent.security.PrincipalUser;
import com.edu.agent.security.SecurityContextHelper;
import com.edu.agent.service.AuditService;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.reflect.MethodSignature;
import org.springframework.core.DefaultParameterNameDiscoverer;
import org.springframework.core.ParameterNameDiscoverer;
import org.springframework.expression.EvaluationContext;
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;
import org.springframework.stereotype.Component;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import java.lang.reflect.Method;
import java.math.BigInteger;
import java.util.HashMap;
import java.util.Map;

/**
 * 审计切面: 拦截 @Auditable 注解方法,在成功返回后写一条 audit_logs。
 *
 * SpEL 上下文变量:
 *   - 方法参数(按名引用,如 #req)
 *   - #result: 返回值
 *   - #actor: 当前用户 email
 *   - #tenantId: 当前租户 ID
 *
 * 失败不写(除非 recordOnFailure=true),但记录一条 error audit。
 */
@Slf4j
@Aspect
@Component
@RequiredArgsConstructor
public class AuditAspect {

    private final AuditService auditService;
    private final SecurityContextHelper securityContext;
    private final ExpressionParser parser = new SpelExpressionParser();
    private final ParameterNameDiscoverer discoverer = new DefaultParameterNameDiscoverer();

    @Around("@annotation(auditable)")
    public Object around(ProceedingJoinPoint pjp, Auditable auditable) throws Throwable {
        Object[] resultHolder = new Object[1];
        boolean success = false;
        try {
            Object result = pjp.proceed();
            resultHolder[0] = result;
            success = true;
            return result;
        } finally {
            if (success || auditable.recordOnFailure()) {
                try {
                    writeAudit(pjp, auditable, success ? resultHolder[0] : null, success);
                } catch (Exception e) {
                    log.warn("audit_write_failed: action={} error={}", auditable.action(), e.getMessage());
                }
            }
        }
    }

    private void writeAudit(ProceedingJoinPoint pjp, Auditable auditable, Object result, boolean success) {
        MethodSignature sig = (MethodSignature) pjp.getSignature();
        Method method = sig.getMethod();
        Object[] args = pjp.getArgs();
        String[] paramNames = discoverer.getParameterNames(method);

        EvaluationContext ctx = new StandardEvaluationContext();
        if (paramNames != null) {
            for (int i = 0; i < paramNames.length && i < args.length; i++) {
                ctx.setVariable(paramNames[i], args[i]);
            }
        }
        if (result != null) ctx.setVariable("result", result);

        PrincipalUser p = securityContext.current().orElse(null);
        String actor = p != null ? p.getEmail() : "anonymous";
        BigInteger tenantId = p != null ? p.getTenantId() : BigInteger.ONE;
        ctx.setVariable("actor", actor);
        ctx.setVariable("tenantId", tenantId);

        String target = eval(auditable.target(), ctx, "");
        Map<String, Object> metadata = evalMap(auditable.metadata(), ctx);
        if (!success) {
            metadata.put("status", "failed");
        }

        HttpServletRequest req = currentRequest();
        String ip = clientIp(req);
        String userAgent = req != null ? req.getHeader("User-Agent") : "";

        auditService.logAction(tenantId, actor, auditable.action(), target, ip, userAgent, metadata);
    }

    private String eval(String spel, EvaluationContext ctx, String fallback) {
        if (spel == null || spel.isBlank()) return fallback;
        try {
            Expression exp = parser.parseExpression(spel);
            Object v = exp.getValue(ctx);
            return v != null ? v.toString() : fallback;
        } catch (Exception e) {
            log.debug("spel_eval_failed: {} error={}", spel, e.getMessage());
            return fallback;
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> evalMap(String spel, EvaluationContext ctx) {
        if (spel == null || spel.isBlank()) return new HashMap<>();
        try {
            Expression exp = parser.parseExpression(spel);
            Object v = exp.getValue(ctx);
            if (v instanceof Map) return new HashMap<>((Map<String, Object>) v);
            Map<String, Object> m = new HashMap<>();
            if (v != null) m.put("value", v);
            return m;
        } catch (Exception e) {
            log.debug("spel_eval_map_failed: {} error={}", spel, e.getMessage());
            return new HashMap<>();
        }
    }

    private HttpServletRequest currentRequest() {
        ServletRequestAttributes attrs = (ServletRequestAttributes) RequestContextHolder.getRequestAttributes();
        return attrs != null ? attrs.getRequest() : null;
    }

    private String clientIp(HttpServletRequest req) {
        if (req == null) return "";
        String xff = req.getHeader("X-Forwarded-For");
        if (xff != null && !xff.isBlank()) return xff.split(",")[0].trim();
        return req.getRemoteAddr();
    }
}
