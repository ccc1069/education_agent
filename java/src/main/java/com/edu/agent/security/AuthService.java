package com.edu.agent.security;

import com.edu.agent.db.entity.Learner;
import com.edu.agent.db.entity.RefreshToken;
import com.edu.agent.db.entity.User;
import com.edu.agent.db.enums.UserRole;
import com.edu.agent.db.repository.LearnerRepository;
import com.edu.agent.db.repository.RefreshTokenRepository;
import com.edu.agent.db.repository.UserRepository;
import com.edu.agent.security.dto.*;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigInteger;
import java.time.Instant;
import java.util.UUID;

/**
 * 认证服务 -- 对齐 Python services/auth_service.py。
 * - 注册(学生 / 教师)
 * - 登录(access + refresh token)
 * - 刷新(单次使用 + 旋转)
 * - 登出(撤销 refresh token)
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AuthService {

    private final UserRepository userRepository;
    private final LearnerRepository learnerRepository;
    private final RefreshTokenRepository tokenRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtUtil jwtUtil;
    private final FailedLoginRecorder failedLoginRecorder;

    @Transactional
    public RegisterResponse registerStudent(String email, String password, String name) {
        if (userRepository.existsByEmail(email)) {
            throw new IllegalArgumentException("该邮箱已注册");
        }
        if (password == null || password.length() < 8) {
            throw new IllegalArgumentException("密码至少 8 位");
        }

        User user = new User();
        user.setEmail(email);
        user.setPasswordHash(passwordEncoder.encode(password));
        user.setRole(UserRole.STUDENT);
        user.setIsActive(true);
        user.setIsVerified(false);
        user.setTenantId(BigInteger.ONE);
        user.setFailedLoginCount(0);

        Learner learner = new Learner();
        learner.setTenantId(BigInteger.ONE);
        learner.setPublicId(generatePublicId());
        learner.setName(name == null ? "" : name);
        learner = learnerRepository.save(learner);

        user.setLearnerId(learner.getId());
        user = userRepository.save(user);

        log.info("Student registered: id={} email={}", user.getId(), email);
        return new RegisterResponse(user.getId(), learner.getPublicId(), "注册成功,请登录");
    }

    @Transactional
    public RegisterStaffResponse registerStaff(String email, String password, UserRole role, String name) {
        if (userRepository.existsByEmail(email)) {
            throw new IllegalArgumentException("该邮箱已注册");
        }
        if (password == null || password.length() < 8) {
            throw new IllegalArgumentException("密码至少 8 位");
        }
        if (role == UserRole.STUDENT) {
            throw new IllegalArgumentException("教师注册不能用 student 角色");
        }

        User user = new User();
        user.setEmail(email);
        user.setPasswordHash(passwordEncoder.encode(password));
        user.setRole(role);
        user.setIsActive(true);
        user.setIsVerified(false);
        user.setTenantId(BigInteger.ONE);
        user.setFailedLoginCount(0);
        user = userRepository.save(user);

        log.info("Staff registered: id={} email={} role={}", user.getId(), email, role);
        return new RegisterStaffResponse(user.getId(), "教职工账号已创建");
    }

    @Transactional
    public TokenResponse login(String email, String password) {
        User user = userRepository.findByEmail(email)
                .orElseThrow(() -> {
                    log.info("Login failed: unknown email {}", email);
                    return new IllegalArgumentException("邮箱或密码错误");
                });

        if (!passwordEncoder.matches(password, user.getPasswordHash())) {
            failedLoginRecorder.increment(user.getId());
            log.info("Login failed: bad password for {}", email);
            throw new IllegalArgumentException("邮箱或密码错误");
        }

        if (!Boolean.TRUE.equals(user.getIsActive())) {
            throw new IllegalArgumentException("账号已停用");
        }

        String accessToken = jwtUtil.createAccessToken(
                user.getId().longValue(), user.getEmail(), user.getRole().value());
        JwtUtil.RefreshTokenIssue refresh = jwtUtil.createRefreshToken(
                user.getId().longValue(), user.getEmail());

        RefreshToken rt = new RefreshToken();
        rt.setUserId(user.getId());
        rt.setTokenHash(refresh.tokenHash());
        rt.setExpiresAt(refresh.expiresAt());
        rt.setRevoked(false);
        tokenRepository.save(rt);

        user.setLastLoginAt(Instant.now());
        user.setFailedLoginCount(0);
        userRepository.save(user);

        String learnerPublicId = resolveLearnerPublicId(user.getLearnerId());
        log.info("Login success: id={} email={}", user.getId(), email);

        return new TokenResponse(
                accessToken,
                refresh.token(),
                "bearer",
                jwtUtil.getAccessExpireSeconds(),
                new UserInfo(user.getId(), user.getEmail(), user.getRole().value(), learnerPublicId)
        );
    }

    @Transactional
    public TokenResponse refresh(String refreshToken) {
        String tokenHash = JwtUtil.hashToken(refreshToken);
        RefreshToken record = tokenRepository.findByTokenHash(tokenHash)
                .orElseThrow(() -> new IllegalArgumentException("无效的刷新令牌"));

        if (Boolean.TRUE.equals(record.getRevoked())) {
            throw new IllegalArgumentException("刷新令牌已撤销");
        }
        if (record.getExpiresAt().isBefore(Instant.now())) {
            throw new IllegalArgumentException("刷新令牌已过期");
        }

        User user = userRepository.findById(record.getUserId())
                .orElseThrow(() -> new IllegalArgumentException("用户不存在"));
        if (!Boolean.TRUE.equals(user.getIsActive())) {
            throw new IllegalArgumentException("用户已停用");
        }

        record.setRevoked(true);
        tokenRepository.save(record);

        String newAccess = jwtUtil.createAccessToken(
                user.getId().longValue(), user.getEmail(), user.getRole().value());
        JwtUtil.RefreshTokenIssue newRefresh = jwtUtil.createRefreshToken(
                user.getId().longValue(), user.getEmail());

        RefreshToken rt = new RefreshToken();
        rt.setUserId(user.getId());
        rt.setTokenHash(newRefresh.tokenHash());
        rt.setExpiresAt(newRefresh.expiresAt());
        rt.setRevoked(false);
        tokenRepository.save(rt);

        String learnerPublicId = resolveLearnerPublicId(user.getLearnerId());
        return new TokenResponse(
                newAccess,
                newRefresh.token(),
                "bearer",
                jwtUtil.getAccessExpireSeconds(),
                new UserInfo(user.getId(), user.getEmail(), user.getRole().value(), learnerPublicId)
        );
    }

    @Transactional
    public void logout(String refreshToken) {
        String tokenHash = JwtUtil.hashToken(refreshToken);
        tokenRepository.findByTokenHash(tokenHash).ifPresent(rt -> {
            rt.setRevoked(true);
            tokenRepository.save(rt);
        });
    }

    public MeResponse me(BigInteger userId) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("用户不存在"));
        String learnerPublicId = resolveLearnerPublicId(user.getLearnerId());
        return new MeResponse(
                user.getId(),
                user.getEmail(),
                user.getRole().value(),
                learnerPublicId,
                user.getTenantId()
        );
    }

    private String resolveLearnerPublicId(BigInteger learnerId) {
        if (learnerId == null) return null;
        return learnerRepository.findById(learnerId)
                .map(Learner::getPublicId)
                .orElse(null);
    }

    private String generatePublicId() {
        return "lrn_" + UUID.randomUUID().toString().replace("-", "").substring(0, 16);
    }
}
