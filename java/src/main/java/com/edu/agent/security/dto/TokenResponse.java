package com.edu.agent.security.dto;

public record TokenResponse(
        String access_token,
        String refresh_token,
        String token_type,
        long expires_in_seconds,
        UserInfo user
) {}
