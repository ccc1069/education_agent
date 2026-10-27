package com.edu.agent.core;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.temporal.ChronoUnit;
import java.util.*;
import java.util.stream.Collectors;

/**
 * SM-2 间隔重复算法 -- Java 实现。
 * <p>
 * 与Python版算法完全一致。
 */
public class SpacedRepetition {

    private static final double MIN_EF = 1.3;
    private static final double MAX_EF = 2.5;

    public static class ReviewItem {
        private final String knowledgeId;
        private double easinessFactor = 2.5;
        private double intervalDays = 0;
        private int repetition = 0;
        private Instant nextReview = Instant.now();
        private int totalReviews = 0;

        public ReviewItem(String knowledgeId) {
            this.knowledgeId = knowledgeId;
        }

        public String getKnowledgeId() { return knowledgeId; }
        public double getEasinessFactor() { return easinessFactor; }
        public double getIntervalDays() { return intervalDays; }
        public int getRepetition() { return repetition; }
        public Instant getNextReview() { return nextReview; }
        public boolean isDue() { return Instant.now().isAfter(nextReview); }

        public long getOverdueDays() {
            if (isDue()) {
                return ChronoUnit.DAYS.between(nextReview, Instant.now());
            }
            return 0;
        }

        void setEasinessFactor(double ef) { this.easinessFactor = ef; }
        void setIntervalDays(double d) { this.intervalDays = d; }
        void setRepetition(int r) { this.repetition = r; }
        void setNextReview(Instant i) { this.nextReview = i; }
        void incrementTotalReviews() { this.totalReviews++; }
    }

    /**
     * SM-2 核心: 根据回答质量(0-5)更新复习计划。
     */
    public ReviewItem review(ReviewItem item, int quality) {
        quality = Math.max(0, Math.min(5, quality));
        item.incrementTotalReviews();

        // 更新 EF
        double newEf = item.getEasinessFactor()
                + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02));
        item.setEasinessFactor(Math.max(MIN_EF, Math.min(MAX_EF, newEf)));

        if (quality < 3) {
            item.setRepetition(0);
            item.setIntervalDays(1);
        } else {
            if (item.getRepetition() == 0) {
                item.setIntervalDays(1);
            } else if (item.getRepetition() == 1) {
                item.setIntervalDays(6);
            } else {
                item.setIntervalDays(item.getIntervalDays() * item.getEasinessFactor());
            }
            item.setRepetition(item.getRepetition() + 1);
        }

        long seconds = (long) (item.getIntervalDays() * 86400);
        item.setNextReview(Instant.now().plus(seconds, ChronoUnit.SECONDS));
        return item;
    }

    /**
     * 获取到期需复习的知识点，按逾期天数降序排列。
     */
    public List<ReviewItem> getDueItems(Map<String, ReviewItem> items) {
        return items.values().stream()
                .filter(ReviewItem::isDue)
                .sorted((a, b) -> Long.compare(b.getOverdueDays(), a.getOverdueDays()))
                .collect(Collectors.toList());
    }

    /**
     * 生成未来 N 天的学习计划。
     *
     * @return Map: date string (YYYY-MM-DD) -> knowledge ID list
     */
    public Map<String, List<String>> getStudySchedule(Map<String, ReviewItem> items, int daysAhead) {
        Map<String, List<String>> schedule = new LinkedHashMap<>();
        LocalDate today = LocalDate.now();

        for (int i = 0; i < daysAhead; i++) {
            LocalDate date = today.plusDays(i);
            String dateKey = date.toString();
            List<String> dueIds = new ArrayList<>();

            for (var entry : items.entrySet()) {
                LocalDate reviewDate = entry.getValue().getNextReview()
                        .atZone(ZoneId.systemDefault()).toLocalDate();
                if (!reviewDate.isAfter(date)) {
                    dueIds.add(entry.getKey());
                }
            }

            if (!dueIds.isEmpty()) {
                schedule.put(dateKey, dueIds);
            }
        }

        return schedule;
    }
}
