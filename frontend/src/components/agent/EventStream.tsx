import { Empty, Typography } from 'antd'
import { motion } from 'motion/react'
import type { AgentEvent } from '@/types/agent'
import { EventCard } from './EventCard'
import { AgentStatus } from './AgentStatus'

const { Text } = Typography

interface EventStreamProps {
  events: AgentEvent[]
  status: 'connecting' | 'open' | 'closed' | 'error'
  emptyHint?: string
  showAgentStatus?: boolean
}

export function EventStream({
  events,
  status,
  emptyHint = '点击下方按钮触发 Agent 事件流',
  showAgentStatus = true,
}: EventStreamProps) {
  return (
    <div className="flex flex-col" style={{ gap: 12 }}>
      {showAgentStatus && <AgentStatus status={status} />}

      <div
        style={{
          background: 'var(--color-card)',
          border: '1px solid var(--color-line)',
          borderRadius: 12,
          padding: 12,
          minHeight: 240,
          maxHeight: '60vh',
          overflowY: 'auto',
        }}
      >
        {events.length === 0 ? (
          <div
            className="flex flex-col items-center justify-center"
            style={{ padding: '32px 16px', minHeight: 200 }}
          >
            <div
              style={{
                width: 40,
                height: 40,
                borderRadius: '50%',
                background: 'var(--color-moss-50)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: 8,
              }}
            >
              <span style={{ color: 'var(--color-moss)', fontFamily: 'var(--font-serif)', fontSize: 18 }}>
                ⌖
              </span>
            </div>
            <Text type="secondary" style={{ fontSize: 13 }}>
              {emptyHint}
            </Text>
          </div>
        ) : (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            {events.map((event, i) => (
              <EventCard key={`${event.timestamp}-${i}`} event={event} index={i} />
            ))}
          </motion.div>
        )}
      </div>
    </div>
  )
}
