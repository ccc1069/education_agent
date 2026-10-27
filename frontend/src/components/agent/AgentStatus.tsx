import { Tag, Tooltip } from 'antd'
import type { AgentSource } from '@/types/agent'
import { AGENT_COLORS, AGENT_LABELS } from '@/types/agent'

interface AgentStatusProps {
  status: 'connecting' | 'open' | 'closed' | 'error'
}

const AGENTS: AgentSource[] = [
  'AssessmentAgent',
  'TutorAgent',
  'CurriculumAgent',
  'HintAgent',
  'EngagementAgent',
  'CriticAgent',
  'DebateAgent',
]

export function AgentStatus({ status }: AgentStatusProps) {
  const connected = status === 'open'
  const statusColor = connected ? '#10B981' : status === 'connecting' ? '#F59E0B' : '#9CA3AF'
  const statusText = connected ? '已连接' : status === 'connecting' ? '连接中' : '未连接'

  return (
    <div
      className="flex items-center justify-between flex-wrap gap-3"
      style={{
        padding: '8px 12px',
        background: 'var(--color-card)',
        border: '1px solid var(--color-line)',
        borderRadius: 8,
      }}
    >
      <div className="flex items-center gap-2 flex-wrap">
        <span style={{ fontSize: 11, color: 'var(--color-mist)', letterSpacing: '0.05em' }}>
          AGENTS
        </span>
        {AGENTS.map((agent) => {
          const color = AGENT_COLORS[agent]
          return (
            <Tooltip key={agent} title={agent}>
              <Tag
                style={{
                  fontSize: 11,
                  margin: 0,
                  padding: '0 6px',
                  lineHeight: '18px',
                  background: `${color}11`,
                  border: `1px solid ${color}33`,
                  color,
                }}
              >
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: '50%',
                    background: color,
                    display: 'inline-block',
                    marginRight: 4,
                  }}
                />
                {AGENT_LABELS[agent]}
              </Tag>
            </Tooltip>
          )
        })}
      </div>
      <div className="flex items-center gap-2">
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: statusColor,
            display: 'inline-block',
            animation: connected ? 'pulse-soft 2s infinite' : 'none',
          }}
        />
        <span style={{ fontSize: 12, color: 'var(--color-mist-dark)' }}>{statusText}</span>
      </div>
    </div>
  )
}
