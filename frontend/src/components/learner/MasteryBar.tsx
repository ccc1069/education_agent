import { Progress, Tooltip, Typography } from 'antd'

const { Text } = Typography

interface MasteryBarProps {
  mastery: number
  showLabel?: boolean
  size?: 'small' | 'default'
  label?: string
}

export function MasteryBar({ mastery, showLabel = true, size = 'default', label }: MasteryBarProps) {
  const percent = Math.round(mastery * 100)
  const color = mastery >= 0.8 ? '#10B981' : mastery >= 0.5 ? '#F59E0B' : '#F43F5E'
  const level =
    mastery >= 0.85 ? 'mastered' : mastery >= 0.65 ? 'proficient' : mastery >= 0.4 ? 'developing' : 'beginner'
  const levelLabel =
    level === 'mastered'
      ? '精通'
      : level === 'proficient'
        ? '熟练'
        : level === 'developing'
          ? '发展中'
          : '入门'

  return (
    <div className="w-full">
      {showLabel && (
        <div className="flex items-center justify-between" style={{ marginBottom: 4 }}>
          <Text style={{ fontSize: size === 'small' ? 11 : 12, color: 'var(--color-mist)' }}>
            {label ?? '掌握度'}
          </Text>
          <div className="flex items-baseline gap-2">
            <Tooltip title={`水平: ${levelLabel}`}>
              <Text
                style={{
                  fontSize: size === 'small' ? 11 : 12,
                  color: 'var(--color-mist-dark)',
                  cursor: 'help',
                }}
              >
                {levelLabel}
              </Text>
            </Tooltip>
            <Text
              className="lumen-mono"
              style={{
                fontSize: size === 'small' ? 12 : 14,
                fontWeight: 600,
                color,
              }}
            >
              {percent}%
            </Text>
          </div>
        </div>
      )}
      <Progress
        percent={percent}
        size={size === 'small' ? 6 : 8}
        strokeColor={color}
        trailColor="#F0F4F1"
        showInfo={false}
      />
    </div>
  )
}
