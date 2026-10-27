package com.edu.agent.core;

import com.edu.agent.db.entity.Event;
import com.edu.agent.db.repository.EventRepository;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigInteger;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.concurrent.locks.ReentrantReadWriteLock;
import java.util.stream.Collectors;

/**
 * 事件历史：内存 last-N + 同步落库 events 表（对齐 Python EventPersistenceService）。
 */
@Service
public class EventHistoryService {

    private static final int MAX_HISTORY = 1000;

    private final List<AgentEvent> history = new ArrayList<>();
    private final ReentrantReadWriteLock lock = new ReentrantReadWriteLock();
    private final EventRepository eventRepository;

    public EventHistoryService(EventRepository eventRepository) {
        this.eventRepository = eventRepository;
    }

    @EventListener
    @Transactional
    public void recordEvent(AgentEvent event) {
        lock.writeLock().lock();
        try {
            if (history.size() >= MAX_HISTORY) {
                history.removeFirst();
            }
            history.add(event);
        } finally {
            lock.writeLock().unlock();
        }
        persist(event);
    }

    private void persist(AgentEvent event) {
        if (eventRepository == null || event.getLearnerId() == null || event.getLearnerId().isBlank()) {
            return;
        }
        Event row = new Event();
        row.setTenantId(BigInteger.ONE);
        row.setPublicId(event.getId());
        row.setType(event.getType().getWireName());
        row.setSource(event.getSourceName() != null ? event.getSourceName() : "unknown");
        row.setLearnerPublicId(event.getLearnerId());
        row.setData(event.getData() != null ? new HashMap<>(event.getData()) : new HashMap<>());
        row.setCorrelationId(event.getCorrelationId());
        row.setTimestamp(Instant.ofEpochMilli(event.getTimestamp()));
        eventRepository.save(row);
    }

    public List<AgentEvent> getHistory(String learnerId, EventType type, int limit) {
        lock.readLock().lock();
        try {
            List<AgentEvent> filtered = history.stream()
                    .filter(e -> learnerId == null || learnerId.equals(e.getLearnerId()))
                    .filter(e -> type == null || type == e.getType())
                    .collect(Collectors.toList());
            if (limit > 0 && filtered.size() > limit) {
                return new ArrayList<>(filtered.subList(filtered.size() - limit, filtered.size()));
            }
            return filtered;
        } finally {
            lock.readLock().unlock();
        }
    }

    public void clearHistory() {
        lock.writeLock().lock();
        try {
            history.clear();
        } finally {
            lock.writeLock().unlock();
        }
    }
}
