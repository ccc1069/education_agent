package com.edu.agent.security;

import com.edu.agent.db.entity.User;
import com.edu.agent.db.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigInteger;

/**
 * 独立事务记录登录失败次数,避免 login() 抛出异常时被回滚。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class FailedLoginRecorder {

    private final UserRepository userRepository;

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void increment(BigInteger userId) {
        userRepository.findById(userId).ifPresent(u -> {
            u.setFailedLoginCount(u.getFailedLoginCount() + 1);
            userRepository.save(u);
            log.debug("Incremented failed login count for user {}: {}", userId, u.getFailedLoginCount());
        });
    }
}
