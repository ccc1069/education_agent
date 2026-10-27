package com.edu.agent.security.dto;

import java.math.BigInteger;

public record RegisterResponse(
        BigInteger user_id,
        String learner_id,
        String message
) {}
