# Go 版 -- 多Agent智能教育系统

> 基于 Go 标准库 + goroutine + channel 实现，对照 Python 的 Mesh 与业务面。  
> **SQLite 默认落盘**（`APP_SQLITE_PATH`，默认 `data/edu.db`）：users、knowledge_states、refresh_tokens、events、submissions、audit_logs、题库/班级/作业（`biz_entities`）、RAG 分块（`rag_chunks`）、critiques。RAG 检索仍用 Mock embedding + 内存向量。主路径与认证形态已向 Python / 前端靠拢，**仍不能当作前端热切换生产后端**（领域模型与 PG 全表域有差）。

## 技术栈

- **HTTP**: Go 1.25 标准库 `net/http`（新路由语法）
- **实时通信**: WebSocket (`gorilla/websocket`) + SSE (Server-Sent Events) + Last-Event-ID 重连 + 原子序号 + 心跳
- **Agent通信**: channel（CSP模型）
- **并发**: goroutine（每个Agent独立goroutine）
- **数据安全**: sync.RWMutex
- **知识图谱**: DAG + Kahn拓扑排序
- **LLM 集成**: net/http 调用 OpenAI 兼容 API,重试 + 熔断 + 降级
- **认证**: JWT HMAC-SHA256（纯标准库；access token 含 `learner_id`，学习主链从 token 推断）
- **持久化**: modernc.org/sqlite（`APP_SQLITE_PATH`；`:memory:` 可不落盘文件）
- **密码**: bcrypt (外部依赖 `golang.org/x/crypto/bcrypt`)
- **加密**: AES-256-GCM PII 加密 (纯标准库)
- **审计**: HMAC-SHA256 链式审计
- **限流**: 滑动窗口 (纯标准库)
- **WebSocket**: gorilla/websocket (外部依赖)
- **Critic**: LLM-as-judge；阈值对齐 Python（`needs_regeneration` 缺省时 `overall <= 3`）；评估写入 `critiques`

## 技术对比

| 维度 | Go 版 | Python 版 | Java 版 |
|------|-------|----------|---------|
| 并发模型 | goroutine (轻量级) | asyncio (协程) | Thread (重量级) |
| 通信 | channel (CSP) | asyncio queue | EventPublisher |
| 内存 | goroutine 仅4KB | 协程较轻量 | 线程约1MB |
| 适合场景 | 高并发、低延迟 | AI/ML 生态 | 强类型、Spring 生态常见 |

## 快速开始

```bash
cd golang
go mod tidy
go run cmd/main.go
# 访问 http://localhost:8081/api/v1/health

# 使用真实 LLM (可选)
APP_LLM_API_KEY=sk-xxx APP_LLM_MODEL=gpt-4o-mini go run cmd/main.go

# 可选：指定 SQLite 路径（默认 data/edu.db；设 :memory: 则不落盘）
APP_SQLITE_PATH=data/edu.db go run cmd/main.go
```

启动后自动种子演示账号：`student@demo.com` / `teacher@demo.com` / `admin@demo.com`，密码 `demo123456`。

## Docker 部署

```bash
# 构建镜像
docker build -t multi-agent-education-go:2.0.0 .

# 运行容器
docker run -d \
  --name go-api \
  -p 8081:8081 \
  -e APP_JWT_SECRET=change-me \
  -e APP_LLM_API_KEY=sk-xxx \
  multi-agent-education-go:2.0.0

# 健康检查
wget --no-verbose --tries=1 --spider http://localhost:8081/health
```

### Dockerfile 说明

多阶段构建：`golang:1.25-alpine` 编译 → `gcr.io/distroless/static-debian12:debug` 运行

- **静态编译**: `CGO_ENABLED=0` + `-ldflags='-w -s'`，无外部依赖
- **Distroless 镜像**: 仅 ~2MB，无 shell/包管理器，攻击面极小
- **非 root 用户**: 以 `nonroot` (uid=65532) 运行
- **健康检查**: `HEALTHCHECK` 探测 `/health`（distroless debug 变体包含 wget）

## 目录结构

```
golang/
├── Dockerfile                      # 多阶段构建 (distroless)
├── .dockerignore                   # 构建忽略规则
├── cmd/main.go                     # 入口（7 Agent + Phase 1/2/3 服务 + 优雅关闭）
├── go.mod                          # x/crypto + websocket + modernc.org/sqlite
├── go.sum
└── internal/
    ├── persist/                    # SQLite：users/states/events/submissions/audit/refresh + biz/RAG/critiques
    ├── agent/                      # 核心 5 Agent + Critic/Debate + RAG/Question
    │   ├── agents.go               # Assessment/Tutor/Curriculum/Hint/Engagement
    │   ├── critic_agent.go         # CriticAgent: LLM-as-judge + critiques 落库 + 自反思
    │   ├── debate_agent.go         # DebateAgent: debate_mode 触发
    │   ├── question_agent.go       # QuestionAgent: 题目生成 + 审核
    │   ├── rag_agent.go            # RAGAgent: 文档摄取 + 语义检索
    │   ├── agent_test.go
    │   ├── question_agent_test.go
    │   └── rag_agent_test.go
    ├── auth/                       # Phase 1: 认证授权
    │   ├── jwt.go                  # JWT HS256（含 learner_id）
    │   ├── password.go             # bcrypt 密码哈希
    │   ├── rbac.go                 # 5 角色 RBAC
    │   ├── middleware.go            # HTTP 认证中间件
    │   ├── refresh_token.go        # 刷新令牌轮换 (SHA-256 哈希存储)
    │   ├── user_store.go           # 用户存储
    │   ├── auth_test.go
    │   ├── refresh_token_test.go
    │   └── user_store_test.go
    ├── tenant/                     # Phase 1: 多租户
    │   ├── context.go              # TenantID context
    │   ├── middleware.go            # X-Tenant-ID 中间件
    │   └── tenant_test.go
    ├── audit/                      # Phase 1: 审计日志
    │   ├── audit_service.go        # HMAC-SHA256 链式审计
    │   └── audit_test.go
    ├── privacy/                    # Phase 1: 隐私合规
    │   ├── crypto.go               # AES-256-GCM PII 加密
    │   ├── pii.go                  # PII 脱敏
    │   ├── consent.go              # 同意管理 + 数据导出 + 账户删除
    │   └── privacy_test.go
    ├── ratelimit/                  # Phase 1: 限流
    │   ├── sliding_window.go       # 滑动窗口限流
    │   ├── middleware.go            # 限流中间件
    │   └── ratelimit_test.go        # 8 tests
    ├── rag/                        # Phase 2: RAG 检索增强
    │   ├── chunking.go             # 文本切块
    │   ├── embedding.go            # Mock embedding (MD5 → 384维)
    │   ├── vector_store.go         # 内存向量存储 + 余弦相似度
    │   ├── rag_service.go          # 文档摄取 + 语义检索
    │   └── rag_test.go              # 8 tests
    ├── question/                   # Phase 2: 题库系统
    │   ├── question_bank.go        # 题目存储 + 审核状态机
    │   ├── question_llm.go         # LLM 出题 + 启发式降级
    │   └── question_test.go         # 7 tests
    ├── teacher/                    # Phase 2: 教师后台
    │   ├── class_service.go        # 班级管理 + 邀请码
    │   ├── assignment_service.go   # 作业管理 + 状态机
    │   ├── dashboard_service.go    # 教师仪表盘
    │   └── teacher_test.go          # 8 tests
    ├── scheduler/                  # Phase 2: 任务调度
    │   ├── task_queue.go           # 异步任务队列 + worker pool
    │   ├── scheduler.go            # 定时任务调度器
    │   ├── cron.go                 # 5 字段 cron 表达式解析
    │   ├── scheduler_test.go        # 调度器测试
    │   └── cron_test.go             # Cron 解析测试
    ├── notification/               # Phase 2: 通知
    │   ├── notification_service.go # 多渠道通知 + 勿扰 + 限流
    │   └── notification_test.go    # 7 tests
    ├── vision/                     # Phase 3: 视觉分析
    │   ├── vision_service.go       # 图像校验 + 多模态 LLM
    │   └── vision_test.go           # 6 tests
    ├── observability/              # Phase 3: 可观测性
    │   ├── logging.go              # 结构化日志
    │   ├── metrics.go              # Prometheus 指标 (JSON + text format)
    │   ├── health.go               # 健康检查 (/health, /ready, /live)
    │   └── observability_test.go    # 8 tests
    ├── llm/                        # LLM 包 (重试+熔断+降级)
    │   ├── types.go, provider.go, openai_provider.go, mock_provider.go
    │   ├── factory.go, service.go, prompts.go
    │   ├── critic_service.go, debate_service.go
    │   └── llm_test.go              # 28 tests
    ├── eventbus/                   # channel 事件总线 (27 种事件类型)
    ├── model/                      # BKT + SM-2 + 知识图谱
    ├── tenant/                     # 多租户 (context + middleware + 服务)
    │   ├── context.go              # TenantID context
    │   ├── middleware.go            # X-Tenant-ID 中间件
    │   ├── tenant_service.go       # 租户 CRUD + 配额管理
    │   └── tenant_test.go           # 7 tests
    └── api/                        # HTTP 路由 + SSE + WebSocket + 中间件链
        ├── handler.go              # 路由注册
        ├── websocket.go            # WebSocket 管理器 (gorilla/websocket)
        ├── sse_manager.go          # 增强型 SSE
        ├── middleware.go           # CORS/Recovery/Logging/Tenant/RateLimit
        └── sse_test.go             # 15 tests
```

## API 端点

### 公开端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/health` | 健康检查 |
| GET | `/health` | 健康详情 (含检查项) |
| GET | `/ready` | 就绪探针 |
| GET | `/live` | 存活探针 |
| GET | `/metrics` | 指标 (JSON 格式) |
| GET | `/metrics/prometheus` | 指标 (Prometheus text format) |

### 认证路由

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/register` | 用户注册 (公开) |
| POST | `/api/v1/auth/register/staff` | Admin 创建教师/管理员 (需 Admin) |
| POST | `/api/v1/auth/login` | 登录 (公开,返回 access + refresh token) |
| POST | `/api/v1/auth/refresh` | 刷新 access token (公开) |
| POST | `/api/v1/auth/logout` | 撤销 refresh token (公开) |
| GET | `/api/v1/auth/me` | 当前用户信息 (需认证) |

### 核心教学端点 (需 JWT)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/submit` | 提交答题结果 |
| POST | `/api/v1/question` | 学生提问 (debate_mode=true 触发辩论) |
| POST | `/api/v1/message` | 学生消息（触发苏格拉底式对话） |
| GET | `/api/v1/events/{learnerID}` | 查询事件历史 |
| GET | `/api/v1/stream/{learnerID}` | SSE 实时事件流 |
| GET | `/api/v1/progress/{learnerID}` | 学习进度 (BKT mastery) |
| GET | `/api/v1/knowledge-graph` | 知识图谱结构 |

### RAG 端点 (需 JWT)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/knowledge-base/documents` | 摄取文档 |
| POST | `/api/v1/knowledge-base/search` | 语义检索 |
| GET | `/api/v1/knowledge-base/documents` | 文档列表 (教师+) |
| GET | `/api/v1/knowledge-base/documents/{id}` | 文档详情 + chunks (教师+) |
| POST | `/api/v1/knowledge-base/documents/{id}/delete` | 删除文档 (教师+) |

### 题库端点 (需 JWT)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/questions/generate` | 生成题目 (教师+) |
| POST | `/api/v1/questions/check` | 检查答案 |
| GET | `/api/v1/questions` | 列出题目 |
| GET | `/api/v1/questions/{id}` | 题目详情 |
| POST | `/api/v1/questions/{id}/status` | 审核状态变更 (教师+) |
| POST | `/api/v1/questions/{id}/delete` | 删除题目 (教师+) |

### 教师后台端点 (教师+, 部分学生可访问)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/teacher/classes` | 创建班级 |
| POST | `/api/v1/teacher/classes/join` | 加入班级 (学生) |
| GET | `/api/v1/teacher/classes` | 列出班级 |
| GET | `/api/v1/teacher/classes/{id}` | 班级详情 |
| GET | `/api/v1/teacher/classes/{id}/members` | 成员列表 |
| POST | `/api/v1/teacher/classes/{id}/members/{lid}/delete` | 移除成员 |
| POST | `/api/v1/teacher/classes/{id}/archive` | 归档班级 |
| POST | `/api/v1/teacher/assignments` | 创建作业 |
| GET | `/api/v1/teacher/assignments` | 作业列表 (教师) |
| GET | `/api/v1/teacher/assignments/mine` | 我的作业 (学生) |
| GET | `/api/v1/teacher/assignments/{id}` | 作业详情 |
| POST | `/api/v1/teacher/assignments/{id}` | 更新作业 |
| POST | `/api/v1/teacher/assignments/{id}/status` | 状态变更 |
| POST | `/api/v1/teacher/assignments/{id}/delete` | 删除作业 |
| GET | `/api/v1/teacher/dashboard/{classID}` | 班级仪表盘 |

### 隐私合规端点 (需 JWT)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/privacy/consent` | 获取同意状态 |
| POST | `/api/v1/privacy/consent` | 记录同意 |
| POST | `/api/v1/privacy/export` | 请求数据导出 |
| GET | `/api/v1/privacy/export/jobs` | 列出导出任务 |
| POST | `/api/v1/privacy/delete` | 请求账户删除 |
| GET | `/api/v1/privacy/delete` | 获取删除状态 |
| POST | `/api/v1/privacy/delete/cancel` | 取消删除 |

### 通知端点 (需 JWT)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/notifications` | 列出通知 |
| GET | `/api/v1/notifications/unread-count` | 未读数量 |
| POST | `/api/v1/notifications/read-all` | 全部标记已读 |
| POST | `/api/v1/notifications/{id}/read` | 单条标记已读 |
| GET | `/api/v1/notifications/preferences` | 获取偏好 |
| POST | `/api/v1/notifications/preferences` | 设置偏好 |

### 管理员端点 (需 Admin)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/audit/logs` | 审计日志 |
| GET | `/api/v1/audit/verify` | 验证审计链 |
| GET | `/api/v1/admin/tasks` | 列出任务 + 队列统计 |
| GET | `/api/v1/admin/tasks/history` | 执行历史 |
| POST | `/api/v1/admin/tasks/trigger/{name}` | 手动触发 |
| GET | `/api/v1/admin/tasks/queue/stats` | 队列统计 |
| GET | `/api/v1/admin/tasks/queue/dead-letters` | 死信队列 |
| POST | `/api/v1/tenants` | 创建租户 |
| GET | `/api/v1/tenants` | 列出租户 |
| GET | `/api/v1/tenants/{id}` | 租户详情 + 配额 |
| POST | `/api/v1/tenants/{id}` | 更新租户 |
| POST | `/api/v1/tenants/{id}/delete` | 删除租户 |
| POST | `/api/v1/tenants/{id}/quota` | 更新配额 |
| POST | `/api/v1/tenants/{id}/quota/reset` | 重置配额 |

### WebSocket

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/ws/{learnerID}?token=JWT` | WebSocket 连接 (心跳 60s/10s pong) |

## 中间件链

```
CORS → Recovery → Logging → Tenant → RateLimit → Auth → handler
```

## SSE 增强功能

- **原子序号**: 每个出站事件附加全局单调 `seq`
- **重连回放**: 客户端传 `Last-Event-ID: N` → 自动回放 seq > N 的事件
- **事件缓存**: 每学习者保留最近 100 条事件 (环形缓冲)
- **心跳**: 每 30s 发送 `:heartbeat\n\n` 注释
- **历史**: 新连接发送最近 10 条 + 后续实时

## 配置

```bash
# LLM
APP_LLM_API_KEY=          # OpenAI API key (可选)
APP_LLM_BASE_URL=https://api.openai.com/v1
APP_LLM_MODEL=gpt-4o-mini
APP_LLM_TIMEOUT=30s
APP_LLM_MAX_TOKENS=1024
APP_LLM_TEMPERATURE=0.7
APP_LLM_MAX_RETRIES=3
APP_LLM_RETRY_BACKOFF=1s
APP_LLM_CB_THRESHOLD=5
APP_LLM_CB_DURATION=60s
APP_LLM_PROVIDER=auto     # auto / openai / mock
APP_LLM_DEBATE_ROUNDS=2

# 认证
APP_JWT_SECRET=           # JWT 签名密钥 (生产环境必填)
```

## 测试

```bash
go test ./... -v              # 全量（当前约 200+ 个 Test* 函数，以 `go test` 输出为准）
go test ./internal/api/...
go test ./internal/auth/...
```

## 与 Python 对照（勿理解为「可替换前端上游」）

| 能力 | Python | Go |
|------|--------|-----|
| 教学 Mesh（Assessment…Engagement） | ✅ | ✅ |
| Critic / Debate | ✅（Critic 阈值 `overall <= 3`） | ✅（同阈值；`critiques` 落库） |
| 另有 RAG/Question Agent | 服务层为主 | 另起 Agent（总数可达 9） |
| LLM | 可配 | 可配；无 Key 则降级 |
| WebSocket / SSE | WS | WS + SSE |
| JWT / RBAC | ✅（PG；`learner_id` 在 token） | ✅（SQLite users；JWT 含 `learner_id`） |
| 持久化 | PostgreSQL | **SQLite**：users/states/events/submissions/audit/refresh + biz_entities + rag_chunks + critiques |
| RAG 路径 | `/knowledge-base/*` | `/knowledge-base/*`（列表/检索形态已对齐） |
| 与本仓库前端契约 | **默认上游** | 主路径已靠拢；领域字段/全表域仍有差，不建议热切换 |
| 健康检查 | ✅ | ✅ |
| 优雅关闭 | ✅ | ✅ |
| Docker 部署 | ✅ | ✅ |
