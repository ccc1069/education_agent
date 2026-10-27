# 前端 — 多 Agent 智能教育系统

> React 19 + TypeScript + Vite 8 + Ant Design 5，对接 **Python** 参考后端（也可 MSW 纯前端演示）。  
> 版本 `2.0.0`。业务页面与 API 客户端按 Python 契约编写；Java / Go 虽有部分同类接口，**路径/字段未必一致，不能热切换当生产后端**。

## 技术栈

| 类别 | 选型 |
|------|------|
| 框架 | React 19 + TypeScript + React Router 7 |
| 构建 | Vite 8（`@` → `src`） |
| UI | Ant Design 5 + Tailwind CSS 3 + CSS 变量主题（`styles/tokens.css`） |
| 数据 | TanStack Query 5 + Axios |
| 状态 | Zustand（认证持久化 localStorage） |
| 动效 | Motion |
| Mock | MSW 2（`VITE_USE_MOCK=true`） |
| 实时 | WebSocket（学习对话事件流） |
| 容器 | 多阶段 Dockerfile（Node 构建 + Nginx SPA） |

## 快速开始

```bash
cd code/frontend
cp .env.example .env
npm install
npm run dev
# 默认 http://localhost:3000（端口占用时 Vite 顺延，如 3002）
```

### 模式 A：纯前端演示（默认 `.env.example`）

```env
VITE_USE_MOCK=true
```

- 启动 MSW，不依赖后端
- Vite **不**把 `/api` 代理到 `:8000`（避免假 JWT 打到真实 API 得到 401）

### 模式 B：对接真实 Python 后端（推荐联调）

```env
VITE_USE_MOCK=false
VITE_API_BASE=/api/v1
# 可选直连 WS: VITE_WS_BASE=ws://localhost:8000
```

后端准备：

```bash
cd code && docker compose up -d postgres redis
cd python && alembic upgrade head && python -m scripts.seed_demo_data
uvicorn api.main:app --reload --port 8000
```

演示账号（密码均为 `demo123456`）：

| 角色 | 邮箱 |
|------|------|
| 学生 | `student@demo.com` |
| 教师 | `teacher@demo.com` |
| 管理员 | `admin@demo.com` |

开发代理（`vite.config.ts`，仅非 Mock）：`/api`、`/ws`、`/health` 等 → `http://localhost:8000`。

## 构建与检查

```bash
npm run lint      # tsc --noEmit
npm run build     # tsc -b && vite build
npm run preview   # 预览 dist
```

## 页面地图

| 路径 | 角色 | 说明 |
|------|------|------|
| `/login` `/register` | 公开 | 登录 / 注册 |
| `/learn` `/learn/:knowledgeId` | 学生等 | 学习中心、苏格拉底对话（WS） |
| `/practice` | 学生等 | 练习题库与批改 |
| `/assignments` | 学生 | 我的作业 |
| `/vision` | 学生等 | 拍题 / 识图分析 |
| `/progress` `/knowledge-graph` | 学生等 | 掌握度、知识图谱 |
| `/notifications` `/profile` | 登录用户 | 通知、个人资料与隐私 |
| `/teacher/classes` | 教师 / 管理员 | 班级与看板 |
| `/teacher/assignments` | 教师 / 管理员 | 布置 / 编辑作业（含示例填入） |
| `/teacher/questions` | 教师 / 管理员 | 题库、LLM 出题（可选 RAG） |
| `/teacher/knowledge-base` | 教师 / 管理员 | RAG 文档入库与语义检索 |
| `/admin/tenants` `/admin/audit` `/admin/tasks` | 管理员 | 租户、审计、定时任务 |

路由守卫：`AuthGuard`（角色）+ `RedirectIfAuthed`（已登录访问登录页时跳转）。

## 目录结构

```
frontend/
├── package.json
├── vite.config.ts          # 别名、端口 3000、按 Mock 开关代理
├── tsconfig.json
├── tailwind.config.ts
├── postcss.config.js
├── Dockerfile / nginx.conf # 生产静态托管 + /api 反代
├── .env.example
├── public/                 # 含 MSW worker
└── src/
    ├── main.tsx            # 入口；按需启动 MSW
    ├── App.tsx             # 路由表
    ├── pages/
    │   ├── auth/
    │   ├── student/
    │   ├── teacher/
    │   └── admin/
    ├── components/         # layout / auth / agent / ui / vision …
    ├── lib/
    │   ├── api/            # Axios 业务客户端（auth、questions、rag、teacher…）
    │   ├── store/          # authStore、uiStore
    │   ├── query/          # QueryClient
    │   ├── ws/             # WebSocket hook
    │   ├── questionContent.ts  # 题干/选项归一化（兼容 {key,text}）
    │   └── antd/           # 主题与 locale
    ├── mocks/              # MSW handlers + 演示数据
    ├── styles/             # tokens / fonts / global
    ├── types/
    └── hooks/
```

## API 约定（与 Python 对齐）

- 业务请求走 `VITE_API_BASE`（默认 `/api/v1`）
- HTTP **仅 GET / POST**（更新、删除对应后端的 `POST ...` / `POST .../delete`）
- 401 时客户端会尝试 refresh；失败则清登录态
- 题目 `content.options` 支持字符串或 `{ key, text }`；详情页与练习页用 `parseQuestionContent` 展示

## 后端切换说明

| 后端 | 默认地址 | 前端适配程度 |
|------|---------|--------------|
| Python（推荐） | `:8000` | 本仓库前端的默认契约（认证、RAG `/knowledge-base`、题库、教师、管理端） |
| Java | `:8080` | 主路径与同步事件分发已向 Python 靠拢；领域字段 / Flyway 全表域仍可能有差，需逐项对照 |
| Go | `:8081` | 主路径、JWT `learner_id`、Token 形态已靠拢；SQLite 落主数据与 critiques；领域模型仍有差，不建议直接替换 Python |

改代理目标：编辑 `vite.config.ts` 的 `server.proxy`，或生产侧改 `nginx.conf`。**仅改上游不够，还要核对客户端路径与响应字段。**

WebSocket：

- Python / Java：`/ws/{learner_public_id}?token=...`（开发可经 Vite 代理）
- Go：同样提供 `/ws/...`，另有 SSE `/api/v1/stream/...`

## Docker

```bash
cd code
docker compose up -d --build frontend
# 访问 http://localhost:3000（容器内 Nginx 反代到 python-api）
```

仅构建前端镜像时，确保同 compose 中 `python-api` 已就绪，或按 `nginx.conf` 调整上游。

## 环境变量

| 变量 | 说明 |
|------|------|
| `VITE_USE_MOCK` | `true` 启用 MSW；`false` 走真实 API |
| `VITE_API_BASE` | API 前缀，默认 `/api/v1` |
| `VITE_WS_BASE` | 可选；直连后端 WS（如 `ws://localhost:8000`） |

上层总览：[../README.md](../README.md)；Python 后端：[../python/README.md](../python/README.md)。
