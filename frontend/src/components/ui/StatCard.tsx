import { Card, Statistic } from 'antd'
import type { ReactNode } from 'react'

interface StatCardProps {
  title: string
  value: number | string
  prefix?: ReactNode
  suffix?: string
  valueStyle?: React.CSSProperties
  loading?: boolean
}

export function StatCard({ title, value, prefix, suffix, valueStyle, loading }: StatCardProps) {
  return (
    <Card bordered={false} className="lumen-card lumen-card-hover" loading={loading}>
      <Statistic
        title={
          <span style={{ fontSize: 12, color: 'var(--color-mist)', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
            {title}
          </span>
        }
        value={value}
        prefix={prefix}
        suffix={suffix}
        valueStyle={{
          fontFamily: 'var(--font-serif)',
          fontWeight: 600,
          color: 'var(--color-ink)',
          ...valueStyle,
        }}
      />
    </Card>
  )
}
