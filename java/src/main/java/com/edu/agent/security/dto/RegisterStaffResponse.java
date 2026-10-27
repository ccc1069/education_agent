package com.edu.agent.security.dto;

import java.math.BigInteger;

public record RegisterStaffResponse(
        BigInteger user_id,
        String message
) {}
