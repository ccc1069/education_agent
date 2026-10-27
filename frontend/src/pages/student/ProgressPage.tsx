import { Card, Col, Empty, Row, Skeleton, Tag, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'motion/react'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { MasteryBar } from '@/components/learner/MasteryBar'
import { StatCard } from '@/components/ui/StatCard'
import { learnerApi } from '@/lib/api/learner'
import { useAuthStore } from '@/lib/store/authStore'

const { Text, Title, Paragraph } = Typography

export default function ProgressPage() {
  const user = useAuthStore((s) => s.user)

  const { data: graphData, isLoading: graphLoading } = useQuery({
    queryKey: ['knowledge-graph'],
    queryFn: () => learnerApi.knowledgeGraph(),
  })

  const { data: progressData, isLoading: progressLoading } = useQuery({
    queryKey: ['progress', user?.learner_id],
    queryFn: () => learnerApi.progress(user!.learner_id!),
    enabled: !!user?.learner_id,
    refetchOnMount: 'always',
  })

  const isLoading = graphLoading || progressLoading
  const nodes = graphData?.nodes ?? []
  const hasNoData = progressData?.status === 'no_data'
  const progress = hasNoData ? {} : progressData?.progress ?? {}
  const weakPoints = hasNoData ? [] : progressData?.weak_points ?? []
  const strongPoints = hasNoData ? [] : progressData?.strong_points ?? []

  // 雷达图数据(取前 8 个知识点)
  const radarNodes = nodes.slice(0, 8)
  const avgMastery = nodes.length
    ? nodes.reduce((acc, n) => acc + (progress[n.id] ?? 0), 0) / nodes.length
    : 0

  return (
    <div className="max-w-6xl mx-auto">
      <PageHeader
        title="学习进度"
        subtitle="BKT 知识追踪 · SM-2 间隔重复 · 进入页面或练习后刷新掌握度"
        loading={isLoading && !graphData}
      />

      <Row gutter={[16, 16]} className="mb-6">
        <Col xs={12} md={6}>
          <StatCard
            title="总知识点"
            value={nodes.length}
            loading={isLoading}
          />
        </Col>
        <Col xs={12} md={6}>
          <StatCard
            title="平均掌握度"
            value={`${(avgMastery * 100).toFixed(0)}%`}
            valueStyle={{ color: 'var(--color-moss)' }}
            loading={isLoading}
          />
        </Col>
        <Col xs={12} md={6}>
          <StatCard
            title="已掌握"
            value={strongPoints.length}
            valueStyle={{ color: '#10B981' }}
            loading={isLoading}
          />
        </Col>
        <Col xs={12} md={6}>
          <StatCard
            title="薄弱点"
            value={weakPoints.length}
            valueStyle={{ color: '#F43F5E' }}
            loading={isLoading}
          />
        </Col>
      </Row>

      {hasNoData ? (
        <EmptyState
          title="还没有学习记录"
          description="前往学习中心开始第一次答题,系统会自动追踪你的知识掌握度"
        />
      ) : (
        <Row gutter={[16, 16]}>
          {/* 雷达图(SVG 简化版) */}
          <Col xs={24} lg={12}>
            <Card bordered={false} className="lumen-card">
              <Title level={5} style={{ marginTop: 0 }}>
                掌握度雷达
              </Title>
              <Text type="secondary" style={{ fontSize: 12 }}>
                前 {radarNodes.length} 个知识点
              </Text>
              <div className="mt-3 flex justify-center">
                <RadarChart nodes={radarNodes} mastery={progress} />
              </div>
            </Card>
          </Col>

          {/* 薄弱/优势列表 */}
          <Col xs={24} lg={12}>
            <Card bordered={false} className="lumen-card">
              <Title level={5} style={{ marginTop: 0 }}>
                薄弱知识点 · 需重点复习
              </Title>
              {weakPoints.length === 0 ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="暂无薄弱点,继续保持!"
                  style={{ padding: '24px 0' }}
                />
              ) : (
                <div className="space-y-3">
                  {weakPoints.map((p) => {
                    const node = nodes.find((n) => n.id === p.id)
                    return (
                      <motion.div
                        key={p.id}
                        initial={{ opacity: 0, x: -8 }}
                        animate={{ opacity: 1, x: 0 }}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <Text strong style={{ fontSize: 13 }}>
                            {node?.name ?? p.id}
                          </Text>
                          <Tag color="error" style={{ fontSize: 11 }}>
                            {(p.mastery * 100).toFixed(0)}%
                          </Tag>
                        </div>
                        <MasteryBar mastery={p.mastery} size="small" showLabel={false} />
                      </motion.div>
                    )
                  })}
                </div>
              )}
            </Card>
          </Col>

          {/* 全部知识点掌握度 */}
          <Col xs={24}>
            <Card bordered={false} className="lumen-card">
              <Title level={5} style={{ marginTop: 0 }}>
                全部知识点 · 掌握度详情
              </Title>
              <Row gutter={[16, 16]}>
                {nodes.map((node, idx) => {
                  const m = progress[node.id] ?? 0
                  return (
                    <Col key={node.id} xs={24} sm={12} md={8}>
                      <motion.div
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: Math.min(idx * 0.02, 0.4) }}
                        style={{
                          padding: 12,
                          border: '1px solid var(--color-line)',
                          borderRadius: 8,
                          background: 'var(--color-paper)',
                        }}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <Text strong style={{ fontSize: 13 }}>
                            {node.name}
                          </Text>
                        </div>
                        <MasteryBar mastery={m} size="small" />
                      </motion.div>
                    </Col>
                  )
                })}
              </Row>
            </Card>
          </Col>
        </Row>
      )}
    </div>
  )
}

// ---------- SVG 雷达图 ----------
function RadarChart({
  nodes,
  mastery,
}: {
  nodes: { id: string; name: string }[]
  mastery: Record<string, number>
}) {
  const size = 320
  const cx = size / 2
  const cy = size / 2
  const r = size / 2 - 50
  const n = nodes.length
  if (n < 3) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="至少需要 3 个知识点才能绘制雷达图"
        style={{ padding: '48px 0' }}
      />
    )
  }

  const angle = (i: number) => (Math.PI * 2 * i) / n - Math.PI / 2

  const grid = [0.25, 0.5, 0.75, 1].map((ratio) => (
    <polygon
      key={ratio}
      points={nodes
        .map((_, i) => {
          const x = cx + Math.cos(angle(i)) * r * ratio
          const y = cy + Math.sin(angle(i)) * r * ratio
          return `${x},${y}`
        })
        .join(' ')}
      fill="none"
      stroke="#E5E7EB"
      strokeWidth={1}
    />
  ))

  const dataPoints = nodes.map((node, i) => {
    const m = mastery[node.id] ?? 0
    const x = cx + Math.cos(angle(i)) * r * m
    const y = cy + Math.sin(angle(i)) * r * m
    return `${x},${y}`
  })

  const axisLabels = nodes.map((node, i) => {
    const x = cx + Math.cos(angle(i)) * (r + 18)
    const y = cy + Math.sin(angle(i)) * (r + 18)
    return (
      <text
        key={node.id}
        x={x}
        y={y}
        textAnchor="middle"
        dominantBaseline="middle"
        style={{ fontSize: 11, fill: 'var(--color-mist-dark)' }}
      >
        {node.name.length > 6 ? node.name.slice(0, 6) + '…' : node.name}
      </text>
    )
  })

  return (
    <svg width={size} height={size} style={{ overflow: 'visible' }}>
      {grid}
      {nodes.map((_, i) => {
        const x = cx + Math.cos(angle(i)) * r
        const y = cy + Math.sin(angle(i)) * r
        return (
          <line
            key={i}
            x1={cx}
            y1={cy}
            x2={x}
            y2={y}
            stroke="#E5E7EB"
            strokeWidth={1}
          />
        )
      })}
      <polygon
        points={dataPoints.join(' ')}
        fill="rgba(27, 67, 50, 0.15)"
        stroke="#1B4332"
        strokeWidth={2}
      />
      {dataPoints.map((pt, i) => {
        const [x, y] = pt.split(',').map(Number)
        return <circle key={i} cx={x} cy={y} r={3} fill="#1B4332" />
      })}
      {axisLabels}
    </svg>
  )
}
