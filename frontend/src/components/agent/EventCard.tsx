import { Card, Tag, Tooltip, Typography } from 'antd'
import { motion } from 'motion/react'
import type { AgentEvent, AgentSource } from '@/types/agent'
import { AGENT_COLORS, AGENT_LABELS, AGENT_DESCRIPTIONS, ENGAGEMENT_LABELS, eventTypeLabel, levelLabel } from '@/types/agent'
import type { EngagementState } from '@/types/agent'
import { formatDateTime, formatTime } from '@/lib/datetime'

const { Text, Paragraph } = Typography

interface EventCardProps {
  event: AgentEvent
  index?: number
}

export function EventCard({ event, index = 0 }: EventCardProps) {
  const color = AGENT_COLORS[event.source as AgentSource] ?? '#6B7280'
  const label = AGENT_LABELS[event.source as AgentSource] ?? event.source
  const description = AGENT_DESCRIPTIONS[event.source as AgentSource] ?? ''
  const data = event.data

  const mastery = typeof data.mastery === 'number' ? (data.mastery as number) : null
  const level = typeof data.level === 'string' ? (data.level as string) : null
  const response = typeof data.response === 'string' ? (data.response as string) : null
  const hint = typeof data.hint_text === 'string' ? (data.hint_text as string) : null
  const messageText = typeof data.message === 'string' ? (data.message as string) : null
  const state = typeof data.state === 'string' ? (data.state as EngagementState) : null
  const overall = typeof data.overall === 'number' ? (data.overall as number) : null
  const consensus = typeof data.consensus === 'string' ? (data.consensus as string) : null
  const nextReview = typeof data.next_review === 'string' ? (data.next_review as string) : null

  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.3, delay: Math.min(index * 0.04, 0.3) }}
    >
      <Card
        size="small"
        bordered={false}
        style={{
          background: 'var(--color-card)',
          border: '1px solid var(--color-line)',
          borderLeft: `3px solid ${color}`,
          borderRadius: 10,
          marginBottom: 8,
        }}
      >
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: color,
                display: 'inline-block',
              }}
            />
            <Text strong style={{ fontSize: 13, color }}>
              {label}
            </Text>
            {description && (
              <Tooltip title={description}>
                <span style={{ fontSize: 11, color: 'var(--color-mist)', cursor: 'help' }}>
                  ·
                </span>
              </Tooltip>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Tag
              style={{
                fontSize: 10,
                margin: 0,
                padding: '0 6px',
                lineHeight: '18px',
                background: 'transparent',
                border: `1px solid ${color}33`,
                color,
              }}
            >
              {eventTypeLabel(event.event_type)}
            </Tag>
            <Text type="secondary" style={{ fontSize: 11 }}>
              {formatTime(event.timestamp)}
            </Text>
          </div>
        </div>

        {response && (
          <Paragraph
            style={{
              margin: 0,
              fontSize: 14,
              lineHeight: 1.6,
              color: 'var(--color-ink)',
            }}
          >
            {response}
          </Paragraph>
        )}

        {hint && (
          <Paragraph
            style={{
              margin: 0,
              fontSize: 13,
              lineHeight: 1.6,
              color: 'var(--color-mist-dark)',
              fontStyle: 'italic',
            }}
          >
            {hint}
          </Paragraph>
        )}

        {messageText && (
          <Text style={{ fontSize: 13, color: 'var(--color-mist-dark)' }}>{messageText}</Text>
        )}

        {consensus && (
          <Paragraph
            style={{
              margin: 0,
              fontSize: 14,
              lineHeight: 1.6,
              padding: 8,
              background: 'var(--color-moss-50)',
              borderRadius: 6,
              borderLeft: `2px solid ${color}`,
            }}
          >
            {consensus}
          </Paragraph>
        )}

        {(mastery !== null || level || state || overall !== null || nextReview) && (
          <div
            className="flex flex-wrap items-center gap-3 mt-2"
            style={{ paddingTop: 6, borderTop: '1px dashed var(--color-line-soft)' }}
          >
            {mastery !== null && (
              <span style={{ fontSize: 12 }}>
                <span style={{ color: 'var(--color-mist)' }}>掌握度 </span>
                <span
                  className="lumen-mono"
                  style={{ fontWeight: 600, color: masteryColor(mastery) }}
                >
                  {(mastery * 100).toFixed(1)}%
                </span>
              </span>
            )}
            {level && (
              <Tag
                color="default"
                style={{ fontSize: 11, margin: 0, padding: '0 6px', lineHeight: '18px' }}
              >
                {levelLabel(level)}
              </Tag>
            )}
            {state && (
              <Tag
                color="default"
                style={{ fontSize: 11, margin: 0, padding: '0 6px', lineHeight: '18px' }}
              >
                状态: {ENGAGEMENT_LABELS[state]}
              </Tag>
            )}
            {overall !== null && (
              <span style={{ fontSize: 12 }}>
                <span style={{ color: 'var(--color-mist)' }}>评审评分 </span>
                <span className="lumen-mono" style={{ fontWeight: 600, color }}>
                  {overall.toFixed(2)}
                </span>
              </span>
            )}
            {nextReview && (
              <span style={{ fontSize: 12, color: 'var(--color-mist)' }}>
                下次复习: {formatDateTime(nextReview, 'MM-DD HH:mm')}
              </span>
            )}
          </div>
        )}
      </Card>
    </motion.div>
  )
}

function masteryColor(mastery: number): string {
  if (mastery >= 0.8) return '#10B981'
  if (mastery >= 0.5) return '#F59E0B'
  return '#F43F5E'
}
