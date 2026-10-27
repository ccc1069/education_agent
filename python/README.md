# Python 版 — 多 Agent 智能教育系统

> FastAPI + asyncio + SQLAlchemy 2.0 + Alembic + LLM（OpenAI / MiniMax）参考实现，版本 `2.0.0`  
> 本目录为功能最全的后端：认证、7 Agent、RAG、题库、教师端、隐私、多租户、可观测性。

## 技术栈

| 类别 | 选型 |
|------|------|
| Web | FastAPI + Uvicorn + WebSocket |
| 异步 | asyncio（Python 3.11+） |
| 数据模型 | Pydantic v2 + pydantic-settings |
| 持久化 | SQLAlchemy 2.0 (async) + asyncpg + PostgreSQL 16 |
| 缓存 / 限流 | Redis 7（限流也可退回内存） |
| 迁移 | Alembic（`0001`–`0010`） |
| LLM | OpenAI 兼容 / MiniMax + LangGraph + tenacity |
| Embedding | 独立 `EMBEDDING_*`（DashScope / OpenAI；题目去重 + RAG） |
| 向量检索 | 默认内存 cosine（JSON 存向量）；`USE_PGVECTOR=1` 可切 pgvector |
| 认证 | JWT（access + refresh）+ bcrypt |
| 可观测性 | structlog + Prometheus + OpenTelemetry |
| 调度 | APScheduler + 内存任务队列 |
| 测试 | pytest + pytest-asyncio + factory-boy + aiosqlite（覆盖率门槛 80%） |

## 快速开始

```bash
# 1. 虚拟环境
cd code/python
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. 依赖
pip install -r requirements.txt

# 3. 环境变量（settings 读取本目录 .env）
cp ../.env.example .env
# 必改: JWT_SECRET_KEY、DATABASE_URL
# 出题/对话/Vision: OPENAI_* 或 MINIMAX_*
# RAG/去重建议单独配: EMBEDDING_API_KEY / EMBEDDING_BASE_URL / EMBEDDING_MODEL / EMBEDDING_DIMENSIONS

# 4. 基础设施
cd .. && docker compose up -d postgres redis && cd python

# 5. 迁移
alembic upgrade head

# 6. 演示数据（推荐）
python -m scripts.seed_demo_data
# 仅账号: python -m scripts.seed_demo_users
# 单管理员: python -m scripts.seed_admin --email admin@example.com --password MySecret123

# 7. 启动
uvicorn api.main:app --reload --port 8000
# 或: python -m api.main
# 文档: http://localhost:8000/docs
```

演示账号（`seed_demo_data` 后，密码均为 `demo123456`）：

| 角色 | 邮箱 |
|------|------|
| 学生 | `student@demo.com` |
| 教师 | `teacher@demo.com` |
| 管理员 | `admin@demo.com` |

班级邀请码：`DEMOCLS01` / `DEMOGEO02` / `DEMOADM03`。

完整栈默认会起 go-api/java-api；推荐仅 Python：

```bash
cd .. && docker compose up --build -d postgres redis migrate python-api frontend
docker compose exec python-api python -m scripts.seed_demo_data
```

## 运行测试

```bash
python -m pytest tests/ -v
# pytest.ini 已配 cov，失败门槛 --cov-fail-under=80
```

## Agent 架构

事件驱动 Mesh：Agent 经 EventBus 通信，不直接互相调用。编排器初始化 **7** 个 Agent：

| Agent | 职责 |
|-------|------|
| Assessment | BKT 贝叶斯知识追踪 |
| Tutor | 苏格拉底式教学（可接 LLM） |
| Curriculum | SM-2 + 知识图谱路径规划 |
| Hint | 三级提示（概念 → 方法 → 步骤） |
| Engagement | 学习状态监测 |
| Critic | 旁路评估 Tutor 回复（LLM-as-judge；缺省 `overall <= 3` 触发自反思；表 `critiques`） |
| Debate | 多 persona 辩论（`debate_mode=True` 触发） |

启动时注册定时任务：到期账号删除、复习提醒、过期 token 清理、每日统计等。

## HTTP 约定

业务接口前缀 `/api/v1`。REST **只使用 GET / POST**：

- 更新：`POST /resource/{id}` 或 `POST /resource/{id}/status`
- 删除：`POST /resource/{id}/delete`
- 除注册 / 登录 / 刷新外，需 `Authorization: Bearer <access_token>`

完整契约以 `/docs` 为准。

## API 概览

| 前缀 / 路径 | 说明 |
|-------------|------|
| `POST /auth/register` `login` `refresh` `logout`，`GET /auth/me` | 认证 |
| `POST /submit` `/question` `/message`，`GET /progress/{id}` `/knowledge-graph` | 学习主链路（`learner_id` 由 JWT 推断；`/question` 可带 `debate_mode`） |
| `/knowledge-base/*` | RAG：上传文本、列表、详情（含分块）、语义检索、删除 |
| `/questions/*` | 列表 / 详情 / `generate`（可选 `use_rag`）/ 状态 / 批改 / 删除 |
| `/teacher/*` | 班级、成员、看板、作业（含 `assignments/mine`、编辑、发布） |
| `/privacy/*` | 同意、导出、删除申请 |
| `/audit/*` | 审计日志（管理员） |
| `/admin/tasks/*` | 任务触发、历史、死信队列（管理员） |
| `/notifications/*` | 通知与偏好 |
| `/tenants/*` | 租户与配额（平台 ADMIN） |
| `POST /vision/analyze` | 图片教学分析 |
| `WS /ws/{learner_public_id}` | 实时推送（query `token`） |

运维探针（无 `/api/v1` 前缀）：

| 路径 | 说明 |
|------|------|
| `GET /health` | 综合健康 |
| `GET /ready` | 就绪（DB + LLM），失败 503 |
| `GET /live` | 存活 |
| `GET /metrics` | Prometheus |

## RAG 与 Embedding

- 入库：粘贴文本 / Markdown → 切块 → Embedding → 写入 `document_chunks`（embedding 为 JSON 数组）
- 检索：query embedding + 默认 `InMemoryVectorStore`（余弦相似度）；默认 `min_score` 见路由（前端检索页常用 0.45）
- 出题：`POST /questions/generate` 且 `use_rag=true` 时检索教材辅助命题；失败会 rollback 会话后降级普通出题
- 种子：`seed_demo_data` 用当前 EmbeddingProvider 写入/校正向量维度，避免 Mock 384 维与线上模型不一致导致召回为空
- pgvector：仅当 `USE_PGVECTOR=1` 且列为 `vector` 类型时启用（当前 schema 默认 JSON，勿贸然开启）

## 目录结构

```
python/
├── Dockerfile
├── requirements.txt
├── alembic.ini
├── pytest.ini / .coveragerc
├── .env                      # 本地配置（gitignore；从 ../.env.example 复制）
├── agents/                   # 7 Agent + BaseAgent（模板方法）
├── api/                      # FastAPI 入口、编排器、路由、WebSocket
├── auth/                     # JWT、密码哈希、依赖注入
├── config/                   # settings（读 python/.env）
├── core/                     # EventBus、BKT、SM-2、图谱、限流、租户、队列、调度
├── db/                       # 异步引擎、session、ORM
├── llm/                      # Provider、Tutor/Critic/Debate/Vision/Question
├── rag/                      # 分块、embedding、vector_store
├── repositories/             # Repository
├── services/                 # 领域服务（auth / rag / question / teacher / …）
├── tasks/                    # 定时任务实现
├── observability/            # 日志、指标、tracing、健康检查
├── migrations/versions/      # 0001–0010
├── scripts/
│   ├── seed_admin.py
│   ├── seed_demo_users.py
│   ├── seed_demo_data.sql    # 幂等 SQL 种子
│   └── seed_demo_data.py     # SQL + RAG embedding + 审计 HMAC 链
└── tests/
```

## 数据模型（主要表）

| 表名 | 说明 |
|------|------|
| `learners` / `users` / `refresh_tokens` | 学习者与认证 |
| `knowledge_nodes` / `knowledge_prerequisites` | 知识图谱 |
| `knowledge_states` | BKT 掌握状态（乐观锁 `version`） |
| `submissions` / `review_schedules` | 答题与 SM-2 复习 |
| `events` / `audit_logs` | 事件溯源与审计链 |
| `documents` / `document_chunks` | RAG 知识库 |
| `questions` | 题目库（含 `content_embedding` 去重） |
| `classes` / `class_members` / `assignments` | 班级与作业 |
| `privacy_consents` / `privacy_deletion_requests` / `data_export_jobs` | 隐私合规 |
| `task_executions` | 定时任务执行记录 |
| `notifications` / `notification_preferences` | 站内通知 |
| `tenants` / `tenant_quotas` | 多租户与配额 |
| `critiques` | Critic 评估记录（schema/ORM 已就绪；Java/Go 运行时写入，Python 写入以源码为准） |

## 持久化与横切能力

- **L1 缓存**：`LearnerModelService` 内存 dict，Agent 同步读写
- **L2 持久化**：请求结束 orchestrator `save()` upsert 到 DB
- **事件溯源**：EventBus `persist_callback` 写 `events` 表
- **乐观锁**：`knowledge_states.version` upsert 自增
- **多租户**：租户上下文 + SQLAlchemy 行级过滤
- **限流**：全局 IP / 登录 / 注册等（Redis 或内存）
- **连接池**：asyncpg，默认 `pool_size=20`
- **审计**：HMAC 链式 `audit_logs`（种子脚本用 `AuditService` 写入）

## 环境变量要点

模板见 `../.env.example`，本地文件为 `python/.env`。

| 变量 | 用途 |
|------|------|
| `DATABASE_URL` | `postgresql+asyncpg://...` |
| `REDIS_URL` | 缓存 / 限流 |
| `JWT_SECRET_KEY` | 认证（生产必须更换） |
| `OPENAI_*` / `MINIMAX_*` | 对话、出题、Vision |
| `EMBEDDING_*` | RAG 与题目语义去重（可与聊天模型分离） |
| `USE_PGVECTOR` | `1` 时尝试 PgVectorStore（需 vector 列） |
| `LLM_PROVIDER=mock` / `ENV=test` | 使用 Mock LLM / Mock Embedding |
| `CORS_ORIGINS` | 跨域 |
| `OTEL_EXPORTER_ENDPOINT` / `ENABLE_TRACING` | 链路追踪 |

上层总览见 [../README.md](../README.md)；前端联调见 [../frontend/README.md](../frontend/README.md)。
