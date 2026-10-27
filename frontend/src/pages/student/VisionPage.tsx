import { useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Input,
  Row,
  Segmented,
  Select,
  Skeleton,
  Slider,
  Tag,
  Typography,
} from 'antd'
import { CameraOutlined, SendOutlined } from '@ant-design/icons'
import { useMutation } from '@tanstack/react-query'
import { motion } from 'motion/react'
import { visionApi } from '@/lib/api/vision'
import { ImageUploader } from '@/components/vision/ImageUploader'
import { PageHeader } from '@/components/ui/PageHeader'
import type { VisionAnalyzeResponse } from '@/types/api'

const { Text, Title, Paragraph } = Typography
const { TextArea } = Input

type Level = 'beginner' | 'developing' | 'proficient' | 'mastered'

const KNOWLEDGE_OPTIONS = [
  { value: 'general', label: '通用' },
  { value: 'arithmetic', label: '四则运算' },
  { value: 'fractions', label: '分数运算' },
  { value: 'algebraic_expr', label: '代数式' },
  { value: 'linear_eq_1', label: '一元一次方程' },
  { value: 'factoring', label: '因式分解' },
  { value: 'quadratic_eq', label: '一元二次方程' },
  { value: 'quadratic_func', label: '二次函数' },
  { value: 'pythagorean', label: '勾股定理' },
  { value: 'probability', label: '概率初步' },
]

export default function VisionPage() {
  const { message } = App.useApp()
  const [images, setImages] = useState<string[]>([])
  const [knowledgeId, setKnowledgeId] = useState('general')
  const [level, setLevel] = useState<Level>('beginner')
  const [mastery, setMastery] = useState(0)
  const [learnerMessage, setLearnerMessage] = useState('')
  const [result, setResult] = useState<VisionAnalyzeResponse | null>(null)

  const mutation = useMutation({
    mutationFn: (payload: {
      images: string[]
      knowledge_id: string
      learner_message: string
      level: Level
      mastery: number
    }) => visionApi.analyze(payload),
    onSuccess: (data) => {
      setResult(data)
      message.success('Vision 分析完成')
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        '分析失败,请稍后重试'
      message.error(detail)
    },
  })

  const handleSubmit = () => {
    if (images.length === 0) {
      message.warning('请上传至少一张图片')
      return
    }
    mutation.mutate({
      images,
      knowledge_id: knowledgeId,
      learner_message: learnerMessage,
      level,
      mastery,
    })
  }

  return (
    <div className="max-w-5xl mx-auto">
      <PageHeader
        title="拍题分析"
        subtitle="上传题目图片,Vision Agent 会识别内容并给出教学引导(不会直接给答案)"
        extra={
          <Tag color="default" style={{ fontSize: 12 }}>
            <CameraOutlined /> P2#16c · Vision
          </Tag>
        }
      />

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card bordered={false} className="lumen-card">
            <Title level={5} style={{ marginTop: 0 }}>
              1. 上传题目图片
            </Title>
            <ImageUploader value={images} onChange={setImages} />

            <div className="mt-6">
              <Title level={5}>2. 学习上下文</Title>
              <Row gutter={[12, 12]}>
                <Col xs={24} sm={12}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    当前知识点
                  </Text>
                  <Select
                    className="mt-1 w-full"
                    value={knowledgeId}
                    onChange={setKnowledgeId}
                    options={KNOWLEDGE_OPTIONS}
                  />
                </Col>
                <Col xs={24} sm={12}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    当前水平
                  </Text>
                  <Segmented
                    block
                    className="mt-1"
                    value={level}
                    onChange={(v) => setLevel(v as Level)}
                    options={[
                      { label: '入门', value: 'beginner' },
                      { label: '发展', value: 'developing' },
                      { label: '熟练', value: 'proficient' },
                      { label: '精通', value: 'mastered' },
                    ]}
                  />
                </Col>
                <Col xs={24}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    掌握度: {Math.round(mastery * 100)}%
                  </Text>
                  <Slider
                    min={0}
                    max={1}
                    step={0.05}
                    value={mastery}
                    onChange={setMastery}
                    tooltip={{ formatter: (v) => `${Math.round((v ?? 0) * 100)}%` }}
                  />
                </Col>
                <Col xs={24}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    附加说明(可选)
                  </Text>
                  <TextArea
                    className="mt-1"
                    value={learnerMessage}
                    onChange={(e) => setLearnerMessage(e.target.value)}
                    placeholder="例如:这道题我尝试过,但卡在第二步..."
                    autoSize={{ minRows: 2, maxRows: 4 }}
                    maxLength={500}
                    showCount
                  />
                </Col>
              </Row>
            </div>

            <Button
              type="primary"
              size="large"
              block
              icon={<SendOutlined />}
              className="mt-4"
              loading={mutation.isPending}
              disabled={images.length === 0}
              onClick={handleSubmit}
            >
              分析 {images.length > 0 ? `(${images.length} 张图片)` : ''}
            </Button>
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card bordered={false} className="lumen-card" style={{ minHeight: 480 }}>
            <Title level={5} style={{ marginTop: 0 }}>
              Vision Agent 响应
            </Title>
            {mutation.isPending ? (
              <Skeleton active paragraph={{ rows: 8 }} />
            ) : result ? (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
              >
                <div
                  className="flex items-center gap-2 mb-3"
                  style={{
                    padding: '6px 10px',
                    background: 'var(--color-moss-50)',
                    borderRadius: 6,
                    fontSize: 12,
                  }}
                >
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: 'var(--color-agent-tutor)',
                    }}
                  />
                  <Text style={{ fontSize: 12, color: 'var(--color-moss)' }}>
                    Vision Agent · {String(result.metadata.image_count ?? 0)} 张图片
                    {result.metadata.llm_used ? ' · LLM 已启用' : ' · 模板回复'}
                  </Text>
                </div>
                <Paragraph
                  style={{
                    fontSize: 14,
                    lineHeight: 1.8,
                    color: 'var(--color-ink)',
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {result.response}
                </Paragraph>
              </motion.div>
            ) : (
              <div
                className="flex flex-col items-center justify-center"
                style={{ padding: '48px 16px', color: 'var(--color-mist)' }}
              >
                <CameraOutlined style={{ fontSize: 40, marginBottom: 8, opacity: 0.4 }} />
                <Text type="secondary" style={{ fontSize: 13 }}>
                  上传图片后点击"分析",响应将在此显示
                </Text>
              </div>
            )}
          </Card>

          <Alert
            type="info"
            showIcon
            className="mt-4"
            message="Vision Agent 不会直接给出答案"
            description={
              <Paragraph style={{ margin: 0, fontSize: 12 }}>
                会通过引导性问题、提示解题思路、指出关键概念来帮助你理解题目。这是苏格拉底式教学的核心。
              </Paragraph>
            }
          />
        </Col>
      </Row>
    </div>
  )
}
