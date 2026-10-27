package com.edu.agent.controller;

import com.edu.agent.db.enums.UserRole;
import com.edu.agent.security.AuthService;
import com.edu.agent.security.PrincipalUser;
import com.edu.agent.security.dto.*;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * 认证路由 -- 对齐 Python /api/v1/auth/*。
 * 公开端点: /login /register /refresh
 * 受保护: /me /logout /register/staff
 */
@RestController
@RequestMapping("/api/v1/auth")
@RequiredArgsConstructor
public class AuthController {

    private final AuthService authService;

    @PostMapping("/register")
    @ResponseStatus(HttpStatus.CREATED)
    public Map<String, Object> register(@Valid @RequestBody RegisterRequest req) {
        RegisterResponse res = authService.registerStudent(req.email(), req.password(), req.name());
        return Map.of(
                "success", true,
                "data", res
        );
    }

    @PostMapping("/register/staff")
    @PreAuthorize("hasRole('ADMIN')")
    @ResponseStatus(HttpStatus.CREATED)
    public Map<String, Object> registerStaff(@Valid @RequestBody RegisterStaffRequest req) {
        UserRole role;
        try {
            role = UserRole.fromValue(req.role());
        } catch (IllegalArgumentException e) {
            throw new IllegalArgumentException("无效的角色: " + req.role());
        }
        RegisterStaffResponse res = authService.registerStaff(req.email(), req.password(), role, req.name());
        return Map.of(
                "success", true,
                "data", res
        );
    }

    @PostMapping("/login")
    public Map<String, Object> login(@Valid @RequestBody LoginRequest req) {
        TokenResponse res = authService.login(req.email(), req.password());
        return Map.of(
                "success", true,
                "data", res
        );
    }

    @PostMapping("/refresh")
    public Map<String, Object> refresh(@Valid @RequestBody RefreshRequest req) {
        TokenResponse res = authService.refresh(req.refreshToken());
        return Map.of(
                "success", true,
                "data", res
        );
    }

    @PostMapping("/logout")
    public ResponseEntity<Void> logout(@Valid @RequestBody LogoutRequest req) {
        authService.logout(req.refreshToken());
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/me")
    public Map<String, Object> me(@AuthenticationPrincipal PrincipalUser principal) {
        if (principal == null) {
            return Map.of("success", false, "error", "未认证");
        }
        MeResponse res = authService.me(principal.getId());
        return Map.of(
                "success", true,
                "data", res
        );
    }
}
