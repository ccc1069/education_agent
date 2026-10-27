import { Card, Skeleton } from 'antd'
import type { ReactNode } from 'react'

interface PageHeaderProps {
  title: string
  subtitle?: string
  extra?: ReactNode
  breadcrumbs?: { label: string; path?: string }[]
  loading?: boolean
}

export function PageHeader({ title, subtitle, extra, loading }: PageHeaderProps) {
  if (loading) {
    return (
      <Card bordered={false} style={{ marginBottom: 16 }}>
        <Skeleton active paragraph={{ rows: 1 }} />
      </Card>
    )
  }
  return (
    <div
      className="flex items-start justify-between"
      style={{ marginBottom: 24, gap: 16 }}
    >
      <div>
        <h1
          style={{
            margin: 0,
            fontFamily: 'var(--font-serif)',
            fontWeight: 600,
            fontSize: 28,
            color: 'var(--color-ink)',
            letterSpacing: '-0.02em',
            lineHeight: 1.15,
          }}
        >
          {title}
        </h1>
        {subtitle && (
          <p
            style={{
              marginTop: 6,
              marginBottom: 0,
              color: 'var(--color-mist)',
              fontSize: 14,
            }}
          >
            {subtitle}
          </p>
        )}
      </div>
      {extra && <div>{extra}</div>}
    </div>
  )
}
