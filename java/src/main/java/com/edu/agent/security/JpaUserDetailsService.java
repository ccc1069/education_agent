package com.edu.agent.security;

import com.edu.agent.db.entity.User;
import com.edu.agent.db.repository.LearnerRepository;
import com.edu.agent.db.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

import java.math.BigInteger;

/**
 * Spring Security 加载用户实现。
 * 注意:此实现仅在 JWT 过滤器解析 token 后被调用(用 userId 查库),
 * 不用于密码校验(走 AuthService)。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class JpaUserDetailsService implements UserDetailsService {

    private final UserRepository userRepository;
    private final LearnerRepository learnerRepository;

    @Override
    public UserDetails loadUserByUsername(String emailOrUserId) throws UsernameNotFoundException {
        User user;
        try {
            BigInteger id = new BigInteger(emailOrUserId);
            user = userRepository.findById(id)
                    .orElseThrow(() -> new UsernameNotFoundException("用户不存在"));
        } catch (NumberFormatException e) {
            user = userRepository.findByEmail(emailOrUserId)
                    .orElseThrow(() -> new UsernameNotFoundException("用户不存在"));
        }

        String learnerPublicId = null;
        if (user.getLearnerId() != null) {
            learnerPublicId = learnerRepository.findById(user.getLearnerId())
                    .map(l -> l.getPublicId())
                    .orElse(null);
        }
        return new PrincipalUser(user, learnerPublicId);
    }

    public UserDetails loadByUserId(BigInteger userId) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new UsernameNotFoundException("用户不存在"));
        String learnerPublicId = null;
        if (user.getLearnerId() != null) {
            learnerPublicId = learnerRepository.findById(user.getLearnerId())
                    .map(l -> l.getPublicId())
                    .orElse(null);
        }
        return new PrincipalUser(user, learnerPublicId);
    }
}
