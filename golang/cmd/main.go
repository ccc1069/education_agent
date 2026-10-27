package main

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"multi-agent-education/golang/internal/agent"
	"multi-agent-education/golang/internal/api"
	"multi-agent-education/golang/internal/audit"
	"multi-agent-education/golang/internal/auth"
	"multi-agent-education/golang/internal/eventbus"
	"multi-agent-education/golang/internal/llm"
	"multi-agent-education/golang/internal/notification"
	"multi-agent-education/golang/internal/observability"
	"multi-agent-education/golang/internal/persist"
	"multi-agent-education/golang/internal/privacy"
	"multi-agent-education/golang/internal/question"
	"multi-agent-education/golang/internal/rag"
	"multi-agent-education/golang/internal/scheduler"
	"multi-agent-education/golang/internal/teacher"
	"multi-agent-education/golang/internal/tenant"
	"multi-agent-education/golang/internal/vision"
)

// 多Agent智能教育系统 - Go版入口
//
// Go版使用 goroutine + channel 实现事件驱动，
// 天然适合高并发Agent并行处理。
//
// 7 Agent Mesh:
// - Assessment/Tutor/Curriculum/Hint/Engagement (核心教学)
// - Critic (LLM-as-judge 评估+自反思)
// - Debate (Multi-Agent Debate 辩论共识)
//
// Phase 1: JWT认证 + RBAC + 多租户 + 审计日志 + 限流 + 隐私合规
// Phase 2: RAG + 题库 + 教师后台 + 任务调度 + 通知
// Phase 3: Vision + 结构化日志 + Prometheus指标 + 健康检查
func main() {
	bus := eventbus.New()

	// 初始化 LLM 服务
	llmService := llm.NewLlmService(llm.NewLlmProviderFromEnv())
	log.Printf("[main] LLM provider: %s", llmService.GetProvider().Name())

	// 初始化 7 个 Agent
	assessmentAgent := agent.NewAssessmentAgent(bus)
	tutorAgent := agent.NewTutorAgent(bus)
	curriculumAgent := agent.NewCurriculumAgent(bus)
	hintAgent := agent.NewHintAgent(bus)
	engagementAgent := agent.NewEngagementAgent(bus)
	criticAgent := agent.NewCriticAgent(bus, llmService)
	debateAgent := agent.NewDebateAgent(bus, llmService)

	// 启动所有 Agent
	go assessmentAgent.Start()
	go tutorAgent.Start()
	go curriculumAgent.Start()
	go hintAgent.Start()
	go engagementAgent.Start()
	go criticAgent.Start()
	go debateAgent.Start()

	// JWT 密钥
	jwtSecret := auth.Key([]byte(getEnv("APP_JWT_SECRET", "default-jwt-secret-change-in-production-32bytes!")))

	// 初始化用户存储（可选 SQLite：APP_SQLITE_PATH，默认 data/edu.db）
	userStore := auth.NewUserStore()
	sqlitePath := getEnv("APP_SQLITE_PATH", "data/edu.db")
	persistDB, err := persist.Open(sqlitePath)
	if err != nil {
		log.Printf("[main] SQLite unavailable (%v), fallback to memory-only users/mastery", err)
		persistDB = nil
	} else {
		userStore.SetPersistHook(func(u *auth.User) error { return persistDB.SaveUser(u) })
		if err := persistDB.LoadUsers(userStore); err != nil {
			log.Printf("[main] load users: %v", err)
		}
		if err := persistDB.SeedDemoUsers(userStore); err != nil {
			log.Printf("[main] seed demo users: %v", err)
		} else {
			log.Printf("[main] SQLite ready at %s (users/states/events/submissions/audit/refresh/critiques)", sqlitePath)
		}
		assessmentAgent.SetPersist(persistDB)
		criticAgent.SetPersist(persistDB)
		bus.SetPersist(func(e eventbus.Event) {
			if err := persistDB.AppendEvent(e); err != nil {
				log.Printf("[EventBus] persist event: %v", err)
			}
		})
	}

	// 初始化 Phase 2 服务
	ragService := rag.NewRAGService(rag.NewMockEmbeddingProvider(), rag.NewInMemoryVectorStore())
	questionBank := question.NewQuestionBank()
	questionSvc := question.NewQuestionService(llmService, questionBank)
	classService := teacher.NewClassService()
	assignmentService := teacher.NewAssignmentService()
	dashboardService := teacher.NewDashboardService(classService, assignmentService)

	if persistDB != nil {
		wireBizPersist(persistDB, ragService, questionBank, classService, assignmentService)
	}

	// 初始化 Phase 3 服务
	metrics := observability.NewMetrics()
	healthChecker := observability.NewHealthChecker()
	healthChecker.Register("server", func() error { return nil })
	healthChecker.Register("agents", func() error { return nil })

	// 初始化新增服务 (Phase 1 补齐)
	privacyService := privacy.NewPrivacyService()
	auditService := audit.NewAuditService([]byte(jwtSecret))
	taskQueue := scheduler.NewTaskQueue(4, 100)
	taskQueue.Start(context.Background())
	notificationSvc := notification.NewNotificationService()
	tenantService := tenant.NewTenantService()

	// 初始化刷新令牌存储 (Phase 2)
	refreshStore := auth.NewRefreshTokenStore()
	if persistDB != nil {
		refreshStore.SetPersistHook(func(rt *auth.RefreshToken) error { return persistDB.SaveRefreshToken(rt) })
		if err := persistDB.LoadRefreshTokens(refreshStore); err != nil {
			log.Printf("[main] load refresh tokens: %v", err)
		}
		auditService.SetPersistHook(func(l *audit.AuditLog) error { return persistDB.AppendAuditLog(l) })
		if tail, err := persistDB.LoadAuditTail(); err != nil {
			log.Printf("[main] load audit tail: %v", err)
		} else if tail != "" {
			auditService.SetLastHash(tail)
		}
	}

	// 初始化 WebSocket 管理器 (Phase 3)
	wsManager := api.NewWebSocketManager(bus, jwtSecret)

	// Vision
	visionService := vision.NewVisionService(llmService)

	// 创建 RAG Agent 和题库 Agent
	ragAgent := agent.NewRAGAgent(bus, ragService)
	questionAgent := agent.NewQuestionAgent(bus, questionBank, questionSvc)
	go ragAgent.Start()
	go questionAgent.Start()

	// 创建路由
	router := api.NewRouter(
		bus, assessmentAgent, jwtSecret, llmService,
		ragService, questionBank, classService, assignmentService,
		dashboardService, metrics, healthChecker,
		userStore, refreshStore, privacyService, auditService, taskQueue,
		notificationSvc, tenantService, wsManager, visionService, persistDB,
	)

	// HTTP 服务
	server := &http.Server{
		Addr:    ":8081",
		Handler: router.Setup(),
	}

	// 优雅关闭
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		log.Println("Go Agent Education Server starting on :8081")
		log.Println("Agents: Assessment/Tutor/Curriculum/Hint/Engagement/Critic/Debate")
		log.Println("Phases: 1/2/3 (Enterprise + Teaching + Observability)")
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatal(err)
		}
	}()

	<-stop
	log.Println("[main] Shutting down server...")

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Printf("[main] Server shutdown error: %v", err)
	}
	log.Println("[main] Server stopped gracefully")
}

func getEnv(key, defaultVal string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultVal
}

func wireBizPersist(
	db *persist.DB,
	ragService *rag.RAGService,
	questionBank *question.QuestionBank,
	classService *teacher.ClassService,
	assignmentService *teacher.AssignmentService,
) {
	questionBank.SetPersistHooks(
		func(q question.Question) error { return db.UpsertBiz("question", q.ID, q) },
		func(id string) error { return db.DeleteBiz("question", id) },
	)
	if err := db.LoadBizKind("question", func(_ string, data []byte) error {
		var q question.Question
		if err := json.Unmarshal(data, &q); err != nil {
			return err
		}
		questionBank.Import(q)
		return nil
	}); err != nil {
		log.Printf("[main] load questions: %v", err)
	}

	classService.SetPersistHooks(
		func(c *teacher.Class) error { return db.UpsertBiz("class", c.ID, c) },
		func(id string) error { return db.DeleteBiz("class", id) },
	)
	if err := db.LoadBizKind("class", func(_ string, data []byte) error {
		var c teacher.Class
		if err := json.Unmarshal(data, &c); err != nil {
			return err
		}
		classService.Import(&c)
		return nil
	}); err != nil {
		log.Printf("[main] load classes: %v", err)
	}

	assignmentService.SetPersistHooks(
		func(a *teacher.Assignment) error { return db.UpsertBiz("assignment", a.ID, a) },
		func(id string) error { return db.DeleteBiz("assignment", id) },
	)
	if err := db.LoadBizKind("assignment", func(_ string, data []byte) error {
		var a teacher.Assignment
		if err := json.Unmarshal(data, &a); err != nil {
			return err
		}
		assignmentService.Import(&a)
		return nil
	}); err != nil {
		log.Printf("[main] load assignments: %v", err)
	}

	ragService.SetPersistHooks(
		func(docID string, chunkIDs []string, chunks map[string]rag.Chunk, store *rag.InMemoryVectorStore) error {
			vecs, metas := store.Snapshot()
			for _, cid := range chunkIDs {
				ch := chunks[cid]
				meta := metas[cid]
				if meta == nil {
					meta = ch.Metadata
				}
				if err := db.UpsertRAGChunk(persist.RAGChunkRow{
					ID: cid, DocID: docID, Text: ch.Text, Vector: vecs[cid], Metadata: meta,
				}); err != nil {
					return err
				}
			}
			return nil
		},
		func(docID string) error { return db.DeleteRAGDoc(docID) },
	)
	rows, err := db.LoadRAGChunks()
	if err != nil {
		log.Printf("[main] load rag chunks: %v", err)
		return
	}
	for _, row := range rows {
		if err := ragService.RestoreChunk(row.ID, row.DocID, row.Text, row.Vector, row.Metadata); err != nil {
			log.Printf("[main] restore rag chunk %s: %v", row.ID, err)
		}
	}
	log.Printf("[main] biz persist ready (questions/classes/assignments/rag)")
}
