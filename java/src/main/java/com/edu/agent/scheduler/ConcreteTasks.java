package com.edu.agent.scheduler;

import com.edu.agent.db.entity.AuditLog;
import com.edu.agent.db.entity.RefreshToken;
import com.edu.agent.db.entity.Submission;
import com.edu.agent.db.repository.AuditLogRepository;
import com.edu.agent.db.repository.RefreshTokenRepository;
import com.edu.agent.db.repository.SubmissionRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.HashMap;
import java.util.Map;

/**
 * 具体定时任务 -- 对齐 Python tasks/__init__.py。
 *
 * <p>4 个内置任务:
 * <ul>
 *   <li>cleanupExpiredTokens: 删除过期 30 天且已撤销的 refresh_tokens</li>
 *   <li>generateDailyStats: 生成每日学习统计</li>
 *   <li>executePendingDeletions: 执行到期的账户删除请求</li>
 *   <li>sendReviewReminders: 扫描到期复习计划并推送提醒</li>
 * </ul>
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class ConcreteTasks {

    private final TaskExecutionRunner runner;
    private final RefreshTokenRepository refreshTokenRepository;
    private final SubmissionRepository submissionRepository;
    private final AuditLogRepository auditLogRepository;

    /**
     * 清理过期 refresh_tokens(每天 03:00)。
     * 对齐 Python cleanup_expired_tokens。
     */
    @Scheduled(cron = "${app.scheduler.cleanup-tokens-cron:0 0 3 * * ?}")
    public void cleanupExpiredTokens() {
        runner.run("cleanup_expired_tokens", "scheduler", this::doCleanupTokens);
    }

    @Transactional(readOnly = true)
    public Map<String, Object> doCleanupTokens() {
        Instant cutoff = Instant.now().minus(30, ChronoUnit.DAYS);
        int deleted = refreshTokenRepository.deleteExpiredBefore(cutoff);
        log.info("cleanup_expired_tokens: deleted={}", deleted);
        return Map.of("deleted_tokens", deleted, "cutoff", cutoff.toString());
    }

    /**
     * 生成每日学习统计(每天 00:05)。
     * 对齐 Python generate_daily_stats。
     */
    @Scheduled(cron = "${app.scheduler.daily-stats-cron:0 5 0 * * ?}")
    public void generateDailyStats() {
        runner.run("generate_daily_stats", "scheduler", this::doDailyStats);
    }

    @Transactional(readOnly = true)
    public Map<String, Object> doDailyStats() {
        Instant todayStart = Instant.now().truncatedTo(ChronoUnit.DAYS);
        Instant todayEnd = todayStart.plus(1, ChronoUnit.DAYS);

        var submissions = submissionRepository.findByCreatedAtBetween(todayStart, todayEnd);
        long total = submissions.size();
        long correct = submissions.stream().filter(s -> Boolean.TRUE.equals(s.getIsCorrect())).count();
        long accuracy = total > 0 ? Math.round(10000.0 * correct / total) / 10000 : 0;

        long totalAudit = auditLogRepository.count();

        Map<String, Object> stats = new HashMap<>();
        stats.put("date", todayStart.toString().substring(0, 10));
        stats.put("total_submissions", total);
        stats.put("correct", correct);
        stats.put("accuracy", accuracy);
        stats.put("total_audit_logs", totalAudit);
        log.info("daily_stats: {}", stats);
        return stats;
    }

    /** 手动触发入口(供 API 调用)。 */
    public Map<String, Object> runCleanupNow() {
        return runner.run("cleanup_expired_tokens", "manual", this::doCleanupTokens);
    }

    public Map<String, Object> runDailyStatsNow() {
        return runner.run("generate_daily_stats", "manual", this::doDailyStats);
    }
}
