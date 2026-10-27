package com.edu.agent.security;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import jakarta.annotation.PostConstruct;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;
import java.util.HexFormat;
import java.util.UUID;

/**
 * JWT 工具 -- 对齐 Python auth/jwt.py。
 * HS256 + (sub/email/role/type/iat/exp/jti) payload。
 */
@Slf4j
@Component
public class JwtUtil {

    public static final String TYPE_ACCESS = "access";
    public static final String TYPE_REFRESH = "refresh";

    @Value("${app.jwt.secret:CHANGE_ME_IN_PRODUCTION}")
    private String secret;

    @Value("${app.jwt.algorithm:HS256}")
    private String algorithm;

    @Value("${app.jwt.access-token-expire-minutes:30}")
    private long accessExpireMinutes;

    @Value("${app.jwt.refresh-token-expire-days:7}")
    private long refreshExpireDays;

    private SecretKey key;

    @PostConstruct
    void init() {
        if (secret == null || secret.length() < 32) {
            log.warn("app.jwt.secret 长度不足 32 字符,生产环境必须更换");
        }
        this.key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
    }

    public String createAccessToken(Long userId, String email, String role) {
        Instant now = Instant.now();
        Instant exp = now.plus(Duration.ofMinutes(accessExpireMinutes));
        return Jwts.builder()
                .subject(String.valueOf(userId))
                .claim("email", email)
                .claim("role", role)
                .claim("type", TYPE_ACCESS)
                .claim("jti", UUID.randomUUID().toString())
                .issuedAt(Date.from(now))
                .expiration(Date.from(exp))
                .signWith(key)
                .compact();
    }

    public RefreshTokenIssue createRefreshToken(Long userId, String email) {
        Instant now = Instant.now();
        Instant exp = now.plus(Duration.ofDays(refreshExpireDays));
        String token = Jwts.builder()
                .subject(String.valueOf(userId))
                .claim("email", email)
                .claim("type", TYPE_REFRESH)
                .claim("jti", UUID.randomUUID().toString())
                .issuedAt(Date.from(now))
                .expiration(Date.from(exp))
                .signWith(key)
                .compact();
        return new RefreshTokenIssue(token, hashToken(token), exp);
    }

    public Claims parse(String token) {
        return Jwts.parser()
                .verifyWith(key)
                .build()
                .parseSignedClaims(token)
                .getPayload();
    }

    public TokenData decodeAccessToken(String token) {
        try {
            Claims c = parse(token);
            if (!TYPE_ACCESS.equals(c.get("type"))) {
                log.warn("Wrong token type: {}", c.get("type"));
                return null;
            }
            return new TokenData(
                    Long.parseLong(c.getSubject()),
                    c.get("email", String.class),
                    c.get("role", String.class),
                    c.get("type", String.class),
                    c.get("jti", String.class),
                    c.getExpiration().toInstant()
            );
        } catch (JwtException | IllegalArgumentException e) {
            log.warn("Invalid token: {}", e.getMessage());
            return null;
        }
    }

    public static String hashToken(String token) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] digest = md.digest(token.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (Exception e) {
            throw new IllegalStateException("SHA-256 not available", e);
        }
    }

    public long getAccessExpireSeconds() {
        return Duration.ofMinutes(accessExpireMinutes).getSeconds();
    }

    public record TokenData(Long userId, String email, String role, String tokenType, String jti, Instant expiresAt) {}
    public record RefreshTokenIssue(String token, String tokenHash, Instant expiresAt) {}
}
