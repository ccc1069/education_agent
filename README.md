# 多 Agent 智能教育与个性化学习系统

事件驱动 Mesh + 多语言参考实现：`python/` 为功能完整参考后端，`java/` / `golang/` 对齐核心 Agent 与学习链路，`frontend/` 为统一 React 控制台。

---

## 项目结构

```
code/
├── README.md                 ← 本文件
├── docker-compose.yml        ← Postgres/Redis/migrate + Python/Go/Java API + 前端
├── .env.example              ← 环境变量模板（不含真实密钥）
│
├── python/                   ← 参考实现（功能最全）
│   ├── README.md
│   ├── agents/               ← 7 Agent（含 Critic / Debate）
│   ├── api/                  ← FastAPI + WebSocket
│   ├── auth/                 ← JWT / bcrypt
│   ├── core/                 ← EventBus、BKT、SM-2、知识图谱、限流、租户、调度
│   ├── db/ + migrations/     ← SQLAlchemy 2.0 async + Alembic
│   ├── llm/                  ← OpenAI / MiniMax / Vision / 出题
│   ├── rag/                  ← 分块、Embedding、向量检索
│   ├── services/ + repositories/
│   ├── scripts/              ← seed_admin / seed_demo_data 等
│   └── tests/
│
├── java/                     ← Spring Boot 3 对齐（核心 Agent + REST/WS）
├── golang/                   ← 标准库实现（channel EventBus + WebSocket/SSE）
│
├── frontend/                 ← React + Vite + Ant Design（三端通用 UI）
│   ├── README.md
│   └── src/
│       ├── pages/            ← 学生 / 教师 / 管理员页面
│       ├── lib/api/          ← 业务 API 客户端
│       └── mocks/            ← MSW（VITE_USE_MOCK=true 时纯前端演示）
│
└── helm/multi-agent-edu/     ← Kubernetes 部署 chart
```

---

## 能力一览（以 Python + 前端为准）

| 角色 | 能力 |
|------|------|
| 学生 | 学习中心、苏格拉底对话、练习题库、我的作业、进度、知识图谱、Vision 识图、通知、隐私导出/删除 |
| 教师 | 班级与看板、作业布置、题库（LLM 生成 + RAG 辅助）、RAG 知识库（文本入库 / 语义检索） |
| 管理员 | 租户、审计日志、定时任务 |

核心算法与 Agent：

- **Assessment**：BKT 掌握度
- **Tutor**：苏格拉底引导（可接 LLM）
- **Curriculum**：SM-2 + 知识图谱路径
- **Hint**：三级提示
- **Engagement**：学习状态监测
- **Critic / Debate**：旁路评估与多 persona 辩论（Python）

约定：

- API 统一前缀 `/api/v1`，响应形态多为 `{ success, data, error }` 或路由自定义模型（以 `/docs` 为准）
- Python REST **仅使用 GET / POST**（更新、删除走 `POST ...` 或 `POST .../delete`）
- Embedding 独立配置：`EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` / `EMBEDDING_DIMENSIONS`（题目去重与 RAG）

---

## 快速开始

### 推荐：本地 Python + 前端（联调）

```bash
# 0. 环境变量
cd code
cp .env.example .env
# 至少配置 JWT_SECRET_KEY；出题/RAG/对话需 OPENAI_* 或 MiniMax，以及可选 EMBEDDING_*

# 1. 基础设施
docker compose up -d postgres redis

# 2. 后端
cd python
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m scripts.seed_demo_data   # 演示账号 + 班级/作业/题库/RAG/审计等
uvicorn api.main:app --reload --port 8000
# API 文档: http://localhost:8000/docs

# 3. 前端（另开终端）
cd ../frontend
cp .env.example .env
# 设 VITE_USE_MOCK=false
npm install
npm run dev
# 默认 http://localhost:3000（占用时顺延，如 3002）
```

演示账号（密码均为 `demo123456`）：

| 角色 | 邮箱 |
|------|------|
| 学生 | `student@demo.com` |
| 教师 | `teacher@demo.com` |
| 管理员 | `admin@demo.com` |

班级邀请码（种子数据）：`DEMOCLS01` / `DEMOGEO02` / `DEMOADM03`。

### Java / Go（核心学习链路）

```bash
# Java 21+ / Maven
cd code/java && mvn spring-boot:run
# http://localhost:8080

# Go 1.25+
cd code/golang && go run cmd/main.go
# http://localhost:8081
```

Java / Go 对照实现 Mesh、学习主链与旁路 Agent；主路径（如 `/knowledge-base`、租户/审计前缀）与 JWT `learner_id` 已向 Python / 前端靠拢。Go 默认 SQLite 落主数据、业务 JSON、RAG 分块与 critiques（`APP_SQLITE_PATH`）。**领域模型与 PG 全表域仍不完全一致，不能当作前端热切换生产后端**。细节见各目录 `README.md`。

### Docker Compose 编排

```bash
cd code
cp .env.example .env   # 必填 POSTGRES_PASSWORD、JWT_SECRET_KEY
# 推荐仅 Python 栈（前端默认反代 python-api）:
docker compose up --build -d postgres redis migrate python-api frontend

# 前端:  http://localhost:3000
# Python: http://localhost:8000
```

默认 `docker compose up` 还会启动 `go-api`、`java-api`。服务列表：`postgres`、`redis`、`migrate`、`python-api`、`go-api`、`java-api`、`frontend`。

演示数据需在 API 容器就绪后自行执行，例如：

```bash
docker compose exec python-api python -m scripts.seed_demo_data
```

---

## 前端页面地图

| 路径 | 说明 |
|------|------|
| `/login` `/register` | 登录 / 注册 |
| `/learn` `/learn/:id` | 学习中心与知识点对话 |
| `/practice` | 练习题库 |
| `/assignments` | 学生作业 |
| `/vision` `/progress` `/knowledge-graph` | 识图、进度、图谱 |
| `/notifications` `/profile` | 通知、个人与隐私 |
| `/teacher/classes` | 班级管理与看板 |
| `/teacher/assignments` | 布置 / 编辑作业 |
| `/teacher/questions` | 题库与 LLM 出题 |
| `/teacher/knowledge-base` | RAG 文档与语义检索 |
| `/admin/tenants` `/admin/audit` `/admin/tasks` | 租户、审计、任务 |

纯 UI 演示：`frontend/.env` 设 `VITE_USE_MOCK=true`（MSW），无需后端。

---

## 环境变量要点

见 `code/.env.example`。常用项：

| 变量 | 用途 |
|------|------|
| `DATABASE_URL` | `postgresql+asyncpg://...` |
| `REDIS_URL` | 缓存 / 限流 |
| `JWT_SECRET_KEY` | 认证（生产必须更换） |
| `OPENAI_API_KEY` / `MINIMAX_API_KEY` | 对话、出题、Vision |
| `EMBEDDING_*` | RAG 与题目语义去重（可与聊天模型分离） |
| `CORS_ORIGINS` | 前端跨域 |
| `VITE_USE_MOCK` | 前端是否走 MSW |

---

## 端口一览

| 服务 | 端口 |
|------|------|
| 前端（dev / Docker） | 3000（dev 冲突时顺延） |
| Python API | 8000 |
| Java API | 8080 |
| Go API | 8081 |
| PostgreSQL | 5432 |
| Redis | 6379 |

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [python/README.md](./python/README.md) | Agent、表结构、API 前缀、测试与种子 |
| [frontend/README.md](./frontend/README.md) | 前端启动、Mock、后端切换 |
| [java/README.md](./java/README.md) | Spring Boot 版说明 |
| [golang/README.md](./golang/README.md) | Go 版说明 |
| [helm/multi-agent-edu/README.md](./helm/multi-agent-edu/README.md) | K8s Chart |

仓库文档站点（架构 / 面试 / 部署）在上级 `docs/`，与本目录代码互补。
