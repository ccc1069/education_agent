package com.edu.agent.security.dto;

import java.math.BigInteger;

public record UserInfo(
        BigInteger id,
        String email,
        String role,
        String learner_id
) {}
