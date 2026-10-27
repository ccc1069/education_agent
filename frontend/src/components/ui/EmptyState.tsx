import { Empty } from 'antd'
import type { ReactNode } from 'react'

interface EmptyStateProps {
  title?: string
  description?: string
  action?: ReactNode
  icon?: ReactNode
}

export function EmptyState({ title, description, action, icon }: EmptyStateProps) {
  return (
    <div
      className="flex flex-col items-center justify-center"
      style={{
        padding: '48px 24px',
        background: 'var(--color-card)',
        borderRadius: 12,
        border: '1px dashed var(--color-line)',
      }}
    >
      {icon ?? (
        <div
          style={{
            width: 56,
            height: 56,
            borderRadius: '50%',
            background: 'var(--color-moss-50)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginBottom: 12,
          }}
        >
          <span style={{ fontFamily: 'var(--font-serif)', fontSize: 28, color: 'var(--color-moss)' }}>
            ∅
          </span>
        </div>
      )}
      <h3 style={{ margin: '0 0 4px', fontSize: 16, color: 'var(--color-ink)' }}>
        {title ?? '暂无数据'}
      </h3>
      <p style={{ margin: 0, color: 'var(--color-mist)', fontSize: 13, textAlign: 'center' }}>
        {description ?? '稍后再来看看'}
      </p>
      {action && <div style={{ marginTop: 16 }}>{action}</div>}
    </div>
  )
}
