package com.edu.agent.security.dto;

import java.math.BigInteger;

public record MeResponse(
        BigInteger id,
        String email,
        String role,
        String learner_id,
        BigInteger tenant_id
) {}
