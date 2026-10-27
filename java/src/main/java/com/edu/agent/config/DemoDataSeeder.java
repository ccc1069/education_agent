package com.edu.agent.config;

import com.edu.agent.db.entity.Learner;
import com.edu.agent.db.entity.User;
import com.edu.agent.db.enums.UserRole;
import com.edu.agent.db.repository.LearnerRepository;
import com.edu.agent.db.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.core.annotation.Order;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigInteger;
import java.util.UUID;

/**
 * 启动时种子演示账号，对齐 Python scripts.seed_demo_users。
 * 密码均为 demo123456：student@demo.com / teacher@demo.com / admin@demo.com。
 */
@Slf4j
@Component
@Order(100)
@Profile("!test")
@RequiredArgsConstructor
public class DemoDataSeeder implements ApplicationRunner {

    private static final String DEMO_PASSWORD = "demo123456";

    private final UserRepository userRepository;
    private final LearnerRepository learnerRepository;
    private final PasswordEncoder passwordEncoder;

    @Override
    @Transactional
    public void run(ApplicationArguments args) {
        seed("student@demo.com", UserRole.STUDENT, "李同学");
        seed("teacher@demo.com", UserRole.TEACHER, "王老师");
        seed("admin@demo.com", UserRole.ADMIN, "管理员");
        log.info("演示账号就绪,统一密码: {}", DEMO_PASSWORD);
    }

    private void seed(String email, UserRole role, String name) {
        var existing = userRepository.findByEmail(email);
        if (existing.isPresent()) {
            User user = existing.get();
            if (user.getLearnerId() == null) {
                Learner learner = createLearner(name);
                user.setLearnerId(learner.getId());
                userRepository.save(user);
                log.info("已补绑 learner: {} public_id={}", email, learner.getPublicId());
            } else {
                log.info("已存在,跳过: {} role={}", email, role);
            }
            return;
        }

        Learner learner = createLearner(name);
        User user = new User();
        user.setEmail(email);
        user.setPasswordHash(passwordEncoder.encode(DEMO_PASSWORD));
        user.setRole(role);
        user.setIsActive(true);
        user.setIsVerified(true);
        user.setTenantId(BigInteger.ONE);
        user.setFailedLoginCount(0);
        user.setLearnerId(learner.getId());
        userRepository.save(user);
        log.info("已创建演示账号: {} role={} learner={}", email, role, learner.getPublicId());
    }

    private Learner createLearner(String name) {
        Learner learner = new Learner();
        learner.setTenantId(BigInteger.ONE);
        learner.setPublicId(UUID.randomUUID().toString());
        learner.setName(name);
        return learnerRepository.save(learner);
    }
}
