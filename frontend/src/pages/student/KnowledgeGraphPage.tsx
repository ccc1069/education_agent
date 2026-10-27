import { useMemo } from 'react'
import { Card, Col, Empty, Row, Skeleton, Tag, Tooltip, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { motion } from 'motion/react'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { learnerApi } from '@/lib/api/learner'
import { useAuthStore } from '@/lib/store/authStore'

const { Text, Title } = Typography

interface GraphNode {
  id: string
  name: string
  difficulty: number
  prerequisites: string[]
  mastery: number
}

export default function KnowledgeGraphPage() {
  const user = useAuthStore((s) => s.user)

  const { data: graphData, isLoading } = useQuery({
    queryKey: ['knowledge-graph'],
    queryFn: () => learnerApi.knowledgeGraph(),
  })

  const { data: progressData } = useQuery({
    queryKey: ['progress', user?.learner_id],
    queryFn: () => learnerApi.progress(user!.learner_id!),
    enabled: !!user?.learner_id,
  })

  const nodes: GraphNode[] = useMemo(() => {
    if (!graphData) return []
    const progress = progressData?.status === 'no_data' ? {} : progressData?.progress ?? {}
    return graphData.nodes.map((n) => ({
      ...n,
      mastery: progress[n.id] ?? 0,
    }))
  }, [graphData, progressData])

  return (
    <div className="max-w-7xl mx-auto">
      <PageHeader
        title="知识图谱"
        subtitle="知识点 DAG · 前置关系一目了然,点击节点开始学习"
        loading={isLoading && !graphData}
        extra={
          <Tag color="default" style={{ fontSize: 12 }}>
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: 'var(--color-moss)',
                display: 'inline-block',
                marginRight: 6,
              }}
            />
            Kahn 拓扑排序
          </Tag>
        }
      />

      <Card bordered={false} className="lumen-card mb-4" size="small">
        <div className="flex flex-wrap items-center gap-6">
          <Legend label="入门" color="#F43F5E" hint="< 40%" />
          <Legend label="发展中" color="#F59E0B" hint="40% - 65%" />
          <Legend label="熟练" color="#3B82F6" hint="65% - 80%" />
          <Legend label="精通" color="#10B981" hint="≥ 80%" />
        </div>
      </Card>

      {isLoading ? (
        <Card bordered={false} className="lumen-card">
          <Skeleton active paragraph={{ rows: 8 }} />
        </Card>
      ) : nodes.length === 0 ? (
        <EmptyState title="知识库为空" description="请联系管理员添加知识点" />
      ) : (
        <Card bordered={false} className="lumen-card">
          <GraphView nodes={nodes} />
        </Card>
      )}
    </div>
  )
}

function Legend({ label, color, hint }: { label: string; color: string; hint: string }) {
  return (
    <div className="flex items-center gap-2">
      <span
        style={{
          width: 12,
          height: 12,
          borderRadius: '50%',
          background: color,
          display: 'inline-block',
        }}
      />
      <div>
        <Text style={{ fontSize: 12, fontWeight: 500, color: 'var(--color-ink)' }}>{label}</Text>
        <Text type="secondary" style={{ fontSize: 11, marginLeft: 4 }}>
          {hint}
        </Text>
      </div>
    </div>
  )
}

// ---------- SVG DAG 可视化 ----------
function GraphView({ nodes }: { nodes: GraphNode[] }) {
  const width = Math.max(900, nodes.length * 130)
  const height = 480
  const layerHeight = 90
  const nodeRadius = 28

  // 计算拓扑层级
  const layers = useMemo(() => computeLayers(nodes), [nodes])

  // 计算每个节点位置
  const positions = useMemo(() => {
    const pos: Record<string, { x: number; y: number }> = {}
    const layerCount = layers.length
    const maxNodesInLayer = Math.max(...layers.map((l) => l.length))
    const colSpacing = (width - 100) / Math.max(maxNodesInLayer, 1)
    layers.forEach((layer, layerIdx) => {
      const y = 60 + layerIdx * layerHeight
      const layerWidth = (layer.length - 1) * colSpacing
      const startX = (width - layerWidth) / 2
      layer.forEach((nodeId, i) => {
        pos[nodeId] = { x: startX + i * colSpacing, y }
      })
    })
    return { pos, layerCount }
  }, [layers, width])

  const masteryColor = (m: number) =>
    m >= 0.8 ? '#10B981' : m >= 0.65 ? '#3B82F6' : m >= 0.4 ? '#F59E0B' : '#F43F5E'

  return (
    <div style={{ overflowX: 'auto' }}>
      <svg width={width} height={Math.max(height, layers.length * layerHeight + 60)}>
        {/* 边 */}
        {nodes.map((node) => {
          const fromPos = positions.pos[node.id]
          if (!fromPos) return null
          return node.prerequisites.map((prereq) => {
            const toPos = positions.pos[prereq]
            if (!toPos) return null
            const dx = fromPos.x - toPos.x
            const dy = fromPos.y - toPos.y
            const dist = Math.hypot(dx, dy)
            const ux = dx / dist
            const uy = dy / dist
            const x1 = toPos.x + ux * nodeRadius
            const y1 = toPos.y + uy * nodeRadius
            const x2 = fromPos.x - ux * nodeRadius
            const y2 = fromPos.y - uy * nodeRadius
            const mx = (x1 + x2) / 2
            const my = (y1 + y2) / 2
            return (
              <g key={`${prereq}-${node.id}`}>
                <path
                  d={`M ${x1} ${y1} Q ${mx} ${my - 8} ${x2} ${y2}`}
                  fill="none"
                  stroke="#9CA3AF"
                  strokeWidth={1.5}
                  strokeDasharray="4 4"
                />
                <circle cx={x2} cy={y2} r={2} fill="#9CA3AF" />
              </g>
            )
          })
        })}

        {/* 节点 */}
        {nodes.map((node) => {
          const pos = positions.pos[node.id]
          if (!pos) return null
          const color = masteryColor(node.mastery)
          return (
            <motion.g
              key={node.id}
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.3 }}
            >
              <Link to={`/learn/${node.id}`}>
                <circle
                  cx={pos.x}
                  cy={pos.y}
                  r={nodeRadius}
                  fill="#FFFFFF"
                  stroke={color}
                  strokeWidth={2.5}
                  style={{ cursor: 'pointer' }}
                />
                <circle
                  cx={pos.x}
                  cy={pos.y}
                  r={nodeRadius - 6}
                  fill={color}
                  fillOpacity={0.12}
                  style={{ cursor: 'pointer', pointerEvents: 'all' }}
                />
                <text
                  x={pos.x}
                  y={pos.y - 4}
                  textAnchor="middle"
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    fill: 'var(--color-ink)',
                    fontFamily: 'var(--font-serif)',
                    pointerEvents: 'none',
                  }}
                >
                  {node.name.slice(0, 4)}
                </text>
                <text
                  x={pos.x}
                  y={pos.y + 10}
                  textAnchor="middle"
                  style={{
                    fontSize: 10,
                    fill: color,
                    fontFamily: 'var(--font-mono)',
                    pointerEvents: 'none',
                  }}
                >
                  {(node.mastery * 100).toFixed(0)}%
                </text>
              </Link>
            </motion.g>
          )
        })}
      </svg>
    </div>
  )
}

function computeLayers(nodes: GraphNode[]): string[][] {
  const inDegree: Record<string, number> = {}
  const adj: Record<string, string[]> = {}
  nodes.forEach((n) => {
    inDegree[n.id] = 0
    adj[n.id] = []
  })
  nodes.forEach((n) => {
    n.prerequisites.forEach((p) => {
      if (nodes.find((x) => x.id === p)) {
        adj[p].push(n.id)
        inDegree[n.id]++
      }
    })
  })

  const layers: string[][] = []
  let current = nodes.filter((n) => inDegree[n.id] === 0).map((n) => n.id)
  while (current.length) {
    layers.push(current)
    const next: string[] = []
    current.forEach((id) => {
      adj[id].forEach((neighbor) => {
        inDegree[neighbor]--
        if (inDegree[neighbor] === 0) next.push(neighbor)
      })
    })
    current = next
  }
  return layers
}
