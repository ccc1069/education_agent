# Java 版 -- 多Agent智能教育系统

> 基于 Spring Boot 3 + Spring Event 的实现

## 技术栈

- **框架**: Spring Boot 3.4
- **Agent通信**: Spring ApplicationEventPublisher（发布-订阅）
- **事件分发**: Spring `@EventListener` 同步分发（对齐 Python `await gather`）；REST 返回前主链路事件已入历史
- **可选异步**: `@EnableAsync` 仍保留，供非主链路任务使用
- **数据库**: H2（开发） / PostgreSQL（生产）
- **学习者模型**: L1 内存 + L2 `knowledge_states` CAS 写回；`submissions` / `events` 主链路落库；Critic 写 `critiques`（阈值 `overall <= 3`）
- **演示账号**: 启动自动种子 `*@demo.com` / `demo123456`（`DemoDataSeeder`，`test` profile 除外）
- **构建**: Maven + Java 21
- **迁移**: Flyway
- **可观测性**: Spring Actuator + Micrometer + Prometheus

## 与 Python 版的对比

| 维度 | Python 版 | Java 版 |
|------|----------|---------|
| 事件总线 | 自定义 EventBus (asyncio) | Spring ApplicationEvent |
| 事件等待 | asyncio gather | `@EventListener` 同步分发 |
| 依赖注入 | 手动构造 | Spring IoC 容器 |
| 线程安全 | asyncio 单线程 | ConcurrentHashMap |
| 知识图谱 | KnowledgeGraph (DAG) | KnowledgeGraph (DAG) |
| 链路追踪 | correlation_id | correlation_id |

## 快速开始

```bash
# 需要 Java 21+ 和 Maven 3.9+
cd java
mvn clean install -DskipTests
mvn spring-boot:run

# 访问 http://localhost:8080/api/v1/health
```

## Docker 部署

```bash
# 构建镜像
docker build -t multi-agent-education-java:2.0.0 .

# 运行容器
docker run -d \
  --name java-api \
  -p 8080:8080 \
  -e SPRING_PROFILES_ACTIVE=prod \
  -e DB_URL=jdbc:postgresql://host:5432/edu_agent \
  -e DB_USERNAME=postgres \
  -e DB_PASSWORD=secret \
  -e JWT_SECRET_KEY=change-me \
  multi-agent-education-java:2.0.0

# 健康检查
curl http://localhost:8080/actuator/health
```

### Dockerfile 说明

多阶段构建：`maven:3.9-eclipse-temurin-21-alpine` 打包 → `eclipse-temurin:21-jre-alpine` 运行

- **分层 JAR**: 按变更频率分层（dependencies / loader / application），最大化 Docker 缓存命中率
- **非 root 用户**: 以 `appuser:appgroup` 运行
- **JVM 容器感知**: `-XX:+UseContainerSupport -XX:MaxRAMPercentage=75.0`
- **健康检查**: `HEALTHCHECK` 探测 `/actuator/health`

## 目录结构

```
java/
├── Dockerfile                      # 多阶段构建 (分层 JAR)
├── .dockerignore                   # 构建忽略规则
├── pom.xml                         # Maven 配置 (Spring Boot 3.4 + Java 21)
└── src/main/
    ├── java/com/edu/agent/
    │   ├── EduAgentApplication.java       # Spring Boot 入口
    │   ├── agent/                         # 7个Agent（@EventListener 注解订阅事件）
    │   │   ├── AssessmentAgent.java       # BKT贝叶斯知识追踪，mastery评估
    │   │   ├── TutorAgent.java            # 4级苏格拉底式Prompt
    │   │   ├── CurriculumAgent.java       # SM-2 + 知识图谱拓扑排序
    │   │   ├── HintAgent.java             # 三级提示策略
    │   │   ├── EngagementAgent.java       # 6状态学习检测 + PACE_ADJUSTMENT
    │   │   ├── CriticAgent.java           # LLM-as-judge 评估 + 自反思
    │   │   └── DebateAgent.java           # Multi-Agent Debate 辩论共识
    │   ├── core/                          # 核心模块
    │   │   ├── AgentEvent.java            # 事件模型（含correlation_id链路追踪）
    │   │   ├── EventType.java             # 事件类型枚举（以源码为准）
    │   │   ├── LearnerModel.java          # BKT贝叶斯知识追踪 + Beta分布
    │   │   ├── SpacedRepetition.java      # SM-2算法
    │   │   ├── KnowledgeGraph.java        # 知识图谱 DAG + Kahn拓扑排序（20节点）
    │   │   └── EventHistoryService.java   # 异步事件历史（上限1000条）
    │   ├── controller/                    # REST + WebSocket 控制器
    │   │   ├── AuthController.java        # 认证（登录/注册/刷新/登出/me）
    │   │   ├── LearnerController.java     # 学习者 API
    │   │   ├── TeacherController.java     # 教师后台
    │   │   ├── QuestionController.java    # 题库管理
    │   │   ├── RagController.java         # RAG 知识库
    │   │   ├── NotificationController.java# 通知
    │   │   ├── PrivacyController.java     # 隐私合规
    │   │   ├── TaskController.java        # 任务调度
    │   │   ├── TenantController.java      # 租户管理
    │   │   ├── AuditLogController.java    # 审计日志
    │   │   ├── VisionController.java      # 视觉分析
    │   │   ├── EduWebSocketHandler.java   # WebSocket实时通信
    │   │   └── GlobalExceptionHandler.java# 全局异常处理
    │   ├── security/                      # 安全（JWT/RBAC/PII加密）
    │   │   ├── JwtUtil.java, JwtAuthenticationFilter.java
    │   │   ├── AuthService.java, SecurityConfig.java
    │   │   ├── PiiEncryption.java         # AES-256-GCM PII 加密
    │   │   └── PiiEncryptionConverter.java# JPA AttributeConverter
    │   ├── service/                       # 业务服务层
    │   ├── llm/                           # LLM 集成（重试+熔断+降级）
    │   ├── rag/                           # RAG 检索增强
    │   ├── audit/                         # 审计切面
    │   ├── tenant/                        # 多租户
    │   ├── observability/                 # 可观测性（Correlation ID / Metrics）
    │   ├── ratelimit/                     # 限流
    │   ├── scheduler/                     # 任务调度
    │   ├── db/entity/ + db/repository/    # JPA 实体 + Repository
    │   └── config/                        # 配置（Async / WebSocket / KnowledgeGraph）
    └── resources/
        ├── application.yml                # 主配置（含 test profile）
        └── db/migration/                 # Flyway 迁移脚本
```

## API 端点（节选）

学习主链路示意如下。另有 Auth / Teacher / Question / RAG / Notification / Privacy / Task / Tenant / Audit / Vision 等 Controller，**完整列表以源码为准**。主路径前缀（如 `/knowledge-base`、`/tenants`、`/audit`、隐私 delete/export）已向 Python 对齐；`/submit` / `/question`（可带 `debate_mode`）的 `learner_id` 来自 JWT。对接本仓库前端前仍建议逐项对照响应字段与领域模型。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/health` | 健康检查 |
| POST | `/api/v1/submit` | 提交答题结果（learner 由 JWT 推断） |
| POST | `/api/v1/question` | 学生提问（可选 `debate_mode`） |
| POST | `/api/v1/message` | 学生消息 |
| GET | `/api/v1/progress/{learnerId}` | 查询学习进度 |
| GET | `/api/v1/events/{learnerId}` | 查询事件历史 |
| WS | `/ws/{learnerId}` | WebSocket |

## 可观测性端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/actuator/health` | 健康检查（K8s liveness/readiness） |
| GET | `/actuator/info` | 应用信息 |
| GET | `/actuator/metrics` | Micrometer 指标（JSON） |
| GET | `/actuator/prometheus` | Prometheus 指标（text format） |

## 配置说明

```yaml
# application.yml 关键配置
spring:
  datasource:
    url: ${DB_URL:jdbc:postgresql://localhost:5432/edu_agent}
    username: ${DB_USERNAME:postgres}
    password: ${DB_PASSWORD:postgres}
  jpa:
    hibernate:
      ddl-auto: validate          # 生产用 validate，由 Flyway 管理 schema
  flyway:
    enabled: true
    locations: classpath:db/migration

app:
  jwt:
    secret: ${JWT_SECRET_KEY:CHANGE_ME_IN_PRODUCTION}
    access-token-expire-minutes: 30
    refresh-token-expire-days: 7
  rate-limit:
    enabled: ${RATE_LIMIT_ENABLED:true}
    global-per-min: 100
    login-per-min: 5
```

## 测试

```bash
# 运行单元测试（数量以 `mvn test` 为准；近期约 140+）
mvn test

# 仅运行特定测试
mvn test -Dtest=AssessmentAgentTest
```
