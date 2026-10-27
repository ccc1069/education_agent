package com.edu.agent.core;

/**
 * 事件类型 -- wire 名与 Python EventType.value 对齐（点分字符串）。
 */
public enum EventType {
    STUDENT_SUBMISSION("student.submission"),
    STUDENT_QUESTION("student.question"),
    STUDENT_MESSAGE("student.message"),
    ASSESSMENT_COMPLETE("assessment.complete"),
    MASTERY_UPDATED("assessment.mastery_updated"),
    WEAKNESS_DETECTED("assessment.weakness_detected"),
    TEACHING_RESPONSE("tutor.teaching_response"),
    HINT_NEEDED("tutor.hint_needed"),
    DIFFICULTY_ADJUSTED("tutor.difficulty_adjusted"),
    PATH_UPDATED("curriculum.path_updated"),
    REVIEW_SCHEDULED("curriculum.review_scheduled"),
    NEXT_TOPIC("curriculum.next_topic"),
    HINT_RESPONSE("hint.response"),
    ENGAGEMENT_ALERT("engagement.alert"),
    ENCOURAGEMENT("engagement.encouragement"),
    PACE_ADJUSTMENT("engagement.pace_adjustment"),
    TEACHING_CRITICIZED("tutor.teaching_criticized"),
    DEBATE_CONSENSUS("tutor.debate_consensus");

    private final String wireName;

    EventType(String wireName) {
        this.wireName = wireName;
    }

    public String getWireName() {
        return wireName;
    }

    /** 解析枚举名或点分 wire 名。 */
    public static EventType fromWire(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("event type empty");
        }
        for (EventType t : values()) {
            if (t.wireName.equals(raw) || t.name().equals(raw)) {
                return t;
            }
        }
        throw new IllegalArgumentException("unknown event type: " + raw);
    }
}
