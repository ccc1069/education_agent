package api

import (
	"encoding/json"
	"net/http"
	"time"

	"multi-agent-education/golang/internal/agent"
	"multi-agent-education/golang/internal/auth"
	"multi-agent-education/golang/internal/audit"
	"multi-agent-education/golang/internal/eventbus"
	"multi-agent-education/golang/internal/llm"
	"multi-agent-education/golang/internal/model"
	"multi-agent-education/golang/internal/notification"
	"multi-agent-education/golang/internal/observability"
	"multi-agent-education/golang/internal/persist"
	"multi-agent-education/golang/internal/privacy"
	"multi-agent-education/golang/internal/question"
	"multi-agent-education/golang/internal/rag"
	"multi-agent-education/golang/internal/ratelimit"
	"multi-agent-education/golang/internal/scheduler"
	"multi-agent-education/golang/internal/teacher"
	"multi-agent-education/golang/internal/tenant"
	"multi-agent-education/golang/internal/vision"
)

// Router 路由依赖集合
type Router struct {
	bus               *eventbus.EventBus
	assessment        *agent.AssessmentAgent
	jwtSecret         auth.Key
	llmService        *llm.LlmService
	ragService        *rag.RAGService
	questionBank      *question.QuestionBank
	classService      *teacher.ClassService
	assignmentService *teacher.AssignmentService
	dashboardService  *teacher.DashboardService
	metrics           *observability.Metrics
	healthChecker     *observability.HealthChecker
	userStore         *auth.UserStore
	refreshStore      *auth.RefreshTokenStore
	privacyService    *privacy.PrivacyService
	auditService      *audit.AuditService
	taskQueue         *scheduler.TaskQueue
	notificationSvc   *notification.NotificationService
	tenantService     *tenant.TenantService
	wsManager         *WebSocketManager
	visionService     *vision.VisionService
	persistDB         *persist.DB
}

// NewRouter 创建路由
func NewRouter(
	bus *eventbus.EventBus,
	assessment *agent.AssessmentAgent,
	jwtSecret auth.Key,
	llmService *llm.LlmService,
	ragService *rag.RAGService,
	questionBank *question.QuestionBank,
	classService *teacher.ClassService,
	assignmentService *teacher.AssignmentService,
	dashboardService *teacher.DashboardService,
	metrics *observability.Metrics,
	healthChecker *observability.HealthChecker,
	userStore *auth.UserStore,
	refreshStore *auth.RefreshTokenStore,
	privacyService *privacy.PrivacyService,
	auditService *audit.AuditService,
	taskQueue *scheduler.TaskQueue,
	notificationSvc *notification.NotificationService,
	tenantService *tenant.TenantService,
	wsManager *WebSocketManager,
	visionService *vision.VisionService,
	persistDB *persist.DB,
) *Router {
	return &Router{
		bus: bus, assessment: assessment, jwtSecret: jwtSecret,
		llmService: llmService, ragService: ragService,
		questionBank: questionBank, classService: classService,
		assignmentService: assignmentService, dashboardService: dashboardService,
		metrics: metrics, healthChecker: healthChecker,
		userStore: userStore, refreshStore: refreshStore,
		privacyService: privacyService,
		auditService: auditService, taskQueue: taskQueue,
		notificationSvc: notificationSvc, tenantService: tenantService,
		wsManager: wsManager,
		visionService: visionService,
		persistDB: persistDB,
	}
}

// SetupRouter 配置HTTP路由 (兼容旧接口)
func SetupRouter(bus *eventbus.EventBus, assessment *agent.AssessmentAgent, jwtSecret auth.Key) http.Handler {
	r := &Router{bus: bus, assessment: assessment, jwtSecret: jwtSecret}
	return r.Setup()
}

// Setup 配置路由
func (r *Router) Setup() http.Handler {
	mux := http.NewServeMux()
	sseManager := NewEnhancedSSEManager()

	// 订阅所有事件，推送给SSE客户端
	allEventTypes := []eventbus.EventType{
		eventbus.StudentSubmission, eventbus.StudentQuestion, eventbus.StudentMessage,
		eventbus.AssessmentComplete, eventbus.MasteryUpdated, eventbus.WeaknessDetected,
		eventbus.TeachingResponse, eventbus.HintNeeded, eventbus.DifficultyAdjusted,
		eventbus.PathUpdated, eventbus.ReviewScheduled, eventbus.NextTopic,
		eventbus.HintResponse,
		eventbus.EngagementAlert, eventbus.Encouragement, eventbus.PaceAdjustment,
		eventbus.TeachingCriticized, eventbus.DebateConsensus,
		eventbus.AuditLogged, eventbus.ConsentUpdated, eventbus.UserRegistered,
		eventbus.RAGDocumentIngested, eventbus.QuestionGenerated, eventbus.QuestionAnswered,
		eventbus.AssignmentCreated, eventbus.NotificationSent, eventbus.ClassCreated,
		eventbus.VisionAnalyzed,
	}
	for _, et := range allEventTypes {
		et := et
		r.bus.Subscribe(et, func(event eventbus.Event) {
			sseManager.PublishEvent(event)
		})
	}

	// === 公开路由 ===
	mux.HandleFunc("GET /api/v1/health", func(w http.ResponseWriter, req *http.Request) {
		writeJSON(w, map[string]interface{}{
			"status": "ok", "service": "multi-agent-education-go", "agents": 7,
		})
	})

	// === 认证路由 (注册/登录) ===
	if r.userStore != nil {
		r.setupAuthRoutes(mux)
	}

	// === 可观测性端点 ===
	if r.metrics != nil {
		mux.Handle("GET /metrics", r.metrics) // JSON 格式
		mux.HandleFunc("GET /metrics/prometheus", r.metrics.ServePrometheus) // Prometheus text
	}
	if r.healthChecker != nil {
		mux.HandleFunc("GET /health", r.healthChecker.ServeHTTP)
		mux.HandleFunc("GET /ready", r.healthChecker.ReadyHandler)
		mux.HandleFunc("GET /live", r.healthChecker.LiveHandler)
	}

	// === 认证路由 ===
	authenticated := auth.AuthMiddleware(r.jwtSecret)

	// 核心教学路由
	r.setupCoreRoutes(mux, authenticated, sseManager)

	// RAG 路由
	if r.ragService != nil {
		r.setupRAGRoutes(mux, authenticated)
	}

	// 题库路由
	if r.questionBank != nil {
		r.setupQuestionRoutes(mux, authenticated)
	}

	// 教师后台路由
	if r.classService != nil {
		r.setupTeacherRoutes(mux, authenticated)
	}

	// 隐私合规路由
	if r.privacyService != nil {
		r.setupPrivacyRoutes(mux, authenticated)
	}

	// 审计日志路由
	if r.auditService != nil {
		r.setupAuditRoutes(mux, authenticated)
	}

	// 任务调度路由
	if r.taskQueue != nil {
		r.setupTaskRoutes(mux, authenticated)
	}

	// 通知路由
	if r.notificationSvc != nil {
		r.setupNotificationRoutes(mux, authenticated)
	}

	// 租户管理路由
	if r.tenantService != nil {
		r.setupTenantRoutes(mux, authenticated)
	}

	// Vision 路由
	if r.visionService != nil {
		r.setupVisionRoutes(mux, authenticated)
	}

	// 学习者路由
	r.setupLearnerRoutes(mux, authenticated)

	// WebSocket 路由
	if r.wsManager != nil {
		mux.HandleFunc("GET /ws/{learnerID}", r.wsManager.HandleWS)
	}

	// === 中间件链 ===
	limiter := ratelimit.NewSlidingWindowLimiter(60, 60*time.Second)

	var handler http.Handler = mux
	handler = ratelimit.RateLimitMiddleware(limiter)(handler)
	handler = tenant.TenantMiddleware()(handler)
	handler = RecoveryMiddleware()(handler)
	handler = LoggingMiddleware()(handler)
	handler = CORSMiddleware()(handler)

	return handler
}

// setupCoreRoutes 核心教学路由
func (r *Router) setupCoreRoutes(mux *http.ServeMux, authenticated func(http.Handler) http.Handler, sseManager *EnhancedSSEManager) {
	formatEvents := func(events []eventbus.Event) []map[string]interface{} {
		out := make([]map[string]interface{}, 0, len(events))
		for _, e := range events {
			out = append(out, map[string]interface{}{
				"type":   string(e.Type),
				"source": e.Source,
				"data":   e.Data,
			})
		}
		return out
	}

	requireLearner := func(w http.ResponseWriter, req *http.Request) (string, bool) {
		user := auth.GetUserFromContext(req.Context())
		if user == nil || user.LearnerID == "" {
			http.Error(w, `{"error":"learner_id missing from token"}`, http.StatusUnauthorized)
			return "", false
		}
		return user.LearnerID, true
	}

	// 学生提交答题（learner_id 来自 JWT）
	mux.Handle("POST /api/v1/submit", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		learnerID, ok := requireLearner(w, req)
		if !ok {
			return
		}
		var body struct {
			KnowledgeID string  `json:"knowledge_id"`
			IsCorrect   bool    `json:"is_correct"`
			TimeSpent   float64 `json:"time_spent_seconds"`
		}
		if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		r.bus.Publish(eventbus.Event{
			Type: eventbus.StudentSubmission, Source: "api",
			LearnerID: learnerID,
			Data: map[string]interface{}{
				"knowledge_id":       body.KnowledgeID,
				"is_correct":         body.IsCorrect,
				"time_spent_seconds": body.TimeSpent,
			},
		})

		if r.persistDB != nil {
			_ = r.persistDB.RecordSubmission(learnerID, body.KnowledgeID, body.IsCorrect, body.TimeSpent)
		}

		events := r.bus.GetHistory(learnerID, 10)
		writeJSON(w, map[string]interface{}{
			"status":           "processed",
			"events_triggered": len(events),
			"events":           formatEvents(events),
		})
	})))

	// 学生提问
	mux.Handle("POST /api/v1/question", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		learnerID, ok := requireLearner(w, req)
		if !ok {
			return
		}
		var body struct {
			KnowledgeID string `json:"knowledge_id"`
			Question    string `json:"question"`
			DebateMode  bool   `json:"debate_mode"`
		}
		if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		r.bus.Publish(eventbus.Event{
			Type: eventbus.StudentQuestion, Source: "api",
			LearnerID: learnerID,
			Data: map[string]interface{}{
				"knowledge_id": body.KnowledgeID,
				"question":     body.Question,
				"debate_mode":  body.DebateMode,
			},
		})

		events := r.bus.GetHistory(learnerID, 10)
		writeJSON(w, map[string]interface{}{
			"status":           "processed",
			"events_triggered": len(events),
			"events":           formatEvents(events),
		})
	})))

	// 学生消息
	mux.Handle("POST /api/v1/message", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		learnerID, ok := requireLearner(w, req)
		if !ok {
			return
		}
		var body struct {
			KnowledgeID string `json:"knowledge_id"`
			Message     string `json:"message"`
		}
		if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		if body.KnowledgeID == "" {
			body.KnowledgeID = "general"
		}

		r.bus.Publish(eventbus.Event{
			Type: eventbus.StudentMessage, Source: "api",
			LearnerID: learnerID,
			Data: map[string]interface{}{
				"knowledge_id": body.KnowledgeID,
				"question":     body.Message,
			},
		})

		events := r.bus.GetHistory(learnerID, 10)
		writeJSON(w, map[string]interface{}{
			"status":           "processed",
			"events_triggered": len(events),
			"events":           formatEvents(events),
		})
	})))

	// 事件历史
	mux.Handle("GET /api/v1/events/{learnerID}", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		learnerID := req.PathValue("learnerID")
		events := r.bus.GetHistory(learnerID, 20)
		writeJSON(w, map[string]interface{}{"learner_id": learnerID, "events": events})
	})))

	// SSE 实时事件流
	mux.Handle("GET /api/v1/stream/{learnerID}", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		sseManager.HandleSSE(w, req)
	})))
}

// setupRAGRoutes RAG 路由
func (r *Router) setupRAGRoutes(mux *http.ServeMux, authenticated func(http.Handler) http.Handler) {
	// 摄取文档
	mux.Handle("POST /api/v1/knowledge-base/documents", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		var body struct {
			DocID string `json:"doc_id"`
			Text  string `json:"text"`
		}
		if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		if body.DocID == "" {
			body.DocID = "doc-" + generateShortID()
		}

		count, err := r.ragService.IngestDocument(body.DocID, body.Text)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}

		r.bus.Publish(eventbus.Event{
			Type: eventbus.RAGDocumentIngested, Source: "api",
			Data: map[string]interface{}{"doc_id": body.DocID, "chunks": count},
		})

		writeJSON(w, map[string]interface{}{
			"document_id": body.DocID,
			"is_new":      true,
			"message":     "Document uploaded and indexed",
			"chunks":      count,
		})
	})))

	// 语义检索
	mux.Handle("POST /api/v1/knowledge-base/search", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		var body struct {
			Query string `json:"query"`
			TopK  int    `json:"top_k"`
		}
		if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		results, err := r.ragService.Search(body.Query, body.TopK)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}

		writeJSON(w, results)
	})))

	// 文档列表（对齐 Python：直接返回数组）
	mux.Handle("GET /api/v1/knowledge-base/documents", authenticated(
		auth.RequireMinRole(auth.RoleTeacher)(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
			docs := r.ragService.ListDocuments()
			writeJSON(w, docs)
		}))))

	// 文档详情
	mux.Handle("GET /api/v1/knowledge-base/documents/{id}", authenticated(
		auth.RequireMinRole(auth.RoleTeacher)(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
			id := req.PathValue("id")
			info, chunks, ok := r.ragService.GetDocument(id)
			if !ok {
				http.Error(w, "document not found", http.StatusNotFound)
				return
			}
			writeJSON(w, map[string]interface{}{"doc_id": info.DocID, "chunk_count": info.ChunkCount, "chunks": chunks})
		}))))

	// 删除文档
	mux.Handle("POST /api/v1/knowledge-base/documents/{id}/delete", authenticated(
		auth.RequireMinRole(auth.RoleTeacher)(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
			id := req.PathValue("id")
			if err := r.ragService.DeleteDocument(id); err != nil {
				http.Error(w, err.Error(), http.StatusInternalServerError)
				return
			}
			w.WriteHeader(http.StatusNoContent)
		}))))
}

// setupQuestionRoutes 题库路由
func (r *Router) setupQuestionRoutes(mux *http.ServeMux, authenticated func(http.Handler) http.Handler) {
	// 生成题目
	mux.Handle("POST /api/v1/questions/generate", authenticated(
		auth.RequireMinRole(auth.RoleTeacher)(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
			var body struct {
				Type        string `json:"type"`
				KnowledgeID string `json:"knowledge_id"`
				Level       string `json:"level"`
			}
			if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}

			qs := question.NewQuestionService(r.llmService, r.questionBank)
			q, err := qs.GenerateQuestion(question.QuestionType(body.Type), body.KnowledgeID, body.Level)
			if err != nil {
				http.Error(w, err.Error(), http.StatusInternalServerError)
				return
			}

			r.questionBank.Add(*q)

			r.bus.Publish(eventbus.Event{
				Type: eventbus.QuestionGenerated, Source: "api",
				Data: map[string]interface{}{"question_id": q.ID},
			})

			writeJSON(w, map[string]interface{}{"question": q})
		}))))

	// 检查答案
	mux.Handle("POST /api/v1/questions/check", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		var body struct {
			QuestionID string `json:"question_id"`
			Answer     string `json:"answer"`
		}
		if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		qs := question.NewQuestionService(r.llmService, r.questionBank)
		correct, feedback, err := qs.CheckAnswer(body.QuestionID, body.Answer)
		if err != nil {
			http.Error(w, err.Error(), http.StatusNotFound)
			return
		}

		r.bus.Publish(eventbus.Event{
			Type: eventbus.QuestionAnswered, Source: "api",
			Data: map[string]interface{}{"question_id": body.QuestionID, "correct": correct},
		})

		writeJSON(w, map[string]interface{}{"correct": correct, "feedback": feedback})
	})))

	// 列出题目
	mux.Handle("GET /api/v1/questions", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		knowledgeID := req.URL.Query().Get("knowledge_id")
		questions := r.questionBank.ListByKnowledge(knowledgeID, question.StatusPublished)
		writeJSON(w, map[string]interface{}{"questions": questions})
	})))

	// 题目详情
	mux.Handle("GET /api/v1/questions/{id}", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		id := req.PathValue("id")
		q, ok := r.questionBank.Get(id)
		if !ok {
			http.Error(w, "question not found", http.StatusNotFound)
			return
		}
		writeJSON(w, map[string]interface{}{"question": q})
	})))

	// 题目状态变更
	mux.Handle("POST /api/v1/questions/{id}/status", authenticated(
		auth.RequireMinRole(auth.RoleTeacher)(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
			id := req.PathValue("id")
			var body struct {
				Status string `json:"status"`
			}
			if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}
			if err := r.questionBank.UpdateStatus(id, question.QuestionStatus(body.Status)); err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}
			writeJSON(w, map[string]interface{}{"status": "updated"})
		}))))

	// 删除题目
	mux.Handle("POST /api/v1/questions/{id}/delete", authenticated(
		auth.RequireMinRole(auth.RoleTeacher)(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
			id := req.PathValue("id")
			if err := r.questionBank.Delete(id); err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}
			writeJSON(w, map[string]interface{}{"status": "deleted"})
		}))))
}

// setupTeacherRoutes 教师后台路由
func (r *Router) setupTeacherRoutes(mux *http.ServeMux, authenticated func(http.Handler) http.Handler) {
	teacherOnly := auth.RequireMinRole(auth.RoleTeacher)

	// 创建班级
	mux.Handle("POST /api/v1/teacher/classes", authenticated(teacherOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		var body struct {
			Name string `json:"name"`
		}
		if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		user := auth.GetUserFromContext(req.Context())
		class, err := r.classService.CreateClass(body.Name, user.ID, user.TenantID)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}

		r.bus.Publish(eventbus.Event{
			Type: eventbus.ClassCreated, Source: "api",
			Data: map[string]interface{}{"class_id": class.ID},
		})

		writeJSON(w, map[string]interface{}{"class": class})
	}))))

	// 加入班级
	mux.Handle("POST /api/v1/teacher/classes/join", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		var body struct {
			InviteCode string `json:"invite_code"`
		}
		if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		user := auth.GetUserFromContext(req.Context())
		if err := r.classService.JoinClass(body.InviteCode, user.ID); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		writeJSON(w, map[string]interface{}{"status": "joined"})
	})))

	// 列出班级
	mux.Handle("GET /api/v1/teacher/classes", authenticated(teacherOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		user := auth.GetUserFromContext(req.Context())
		classes := r.classService.ListByTeacher(user.ID)
		writeJSON(w, map[string]interface{}{"classes": classes})
	}))))

	// 创建作业
	mux.Handle("POST /api/v1/teacher/assignments", authenticated(teacherOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		var body struct {
			ClassID     string   `json:"class_id"`
			Title       string   `json:"title"`
			Description string   `json:"description"`
			QuestionIDs []string `json:"question_ids"`
		}
		if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		dueDate := time.Now().Add(7 * 24 * time.Hour)
		assignment, err := r.assignmentService.CreateAssignment(body.ClassID, body.Title, body.Description, body.QuestionIDs, dueDate)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}

		r.bus.Publish(eventbus.Event{
			Type: eventbus.AssignmentCreated, Source: "api",
			Data: map[string]interface{}{"assignment_id": assignment.ID},
		})

		writeJSON(w, map[string]interface{}{"assignment": assignment})
	}))))

	// 仪表盘
	mux.Handle("GET /api/v1/teacher/dashboard/{classID}", authenticated(teacherOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		classID := req.PathValue("classID")
		dashboard := r.dashboardService.GetDashboard(classID)
		writeJSON(w, map[string]interface{}{"dashboard": dashboard})
	}))))

	// 班级详情
	mux.Handle("GET /api/v1/teacher/classes/{id}", authenticated(teacherOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		id := req.PathValue("id")
		class, err := r.classService.GetClass(id)
		if err != nil {
			http.Error(w, err.Error(), http.StatusNotFound)
			return
		}
		writeJSON(w, map[string]interface{}{"class": class})
	}))))

	// 班级成员列表
	mux.Handle("GET /api/v1/teacher/classes/{id}/members", authenticated(teacherOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		id := req.PathValue("id")
		class, err := r.classService.GetClass(id)
		if err != nil {
			http.Error(w, err.Error(), http.StatusNotFound)
			return
		}
		writeJSON(w, map[string]interface{}{"members": class.Members})
	}))))

	// 移除班级成员
	mux.Handle("POST /api/v1/teacher/classes/{id}/members/{learnerID}/delete", authenticated(teacherOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		classID := req.PathValue("id")
		learnerID := req.PathValue("learnerID")
		if err := r.classService.RemoveMember(classID, learnerID); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		writeJSON(w, map[string]interface{}{"status": "removed"})
	}))))

	// 归档班级
	mux.Handle("POST /api/v1/teacher/classes/{id}/archive", authenticated(teacherOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		id := req.PathValue("id")
		if err := r.classService.ArchiveClass(id); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		writeJSON(w, map[string]interface{}{"status": "archived"})
	}))))

	// 作业列表 (教师)
	mux.Handle("GET /api/v1/teacher/assignments", authenticated(teacherOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		user := auth.GetUserFromContext(req.Context())
		classes := r.classService.ListByTeacher(user.ID)
		assignments := r.assignmentService.ListByTeacher(user.ID, classes)
		writeJSON(w, map[string]interface{}{"assignments": assignments})
	}))))

	// 我的作业 (学生)
	mux.Handle("GET /api/v1/teacher/assignments/mine", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		user := auth.GetUserFromContext(req.Context())
		classes := r.classService.ListByStudent(user.ID)
		assignments := r.assignmentService.ListByStudent(user.ID, classes)
		writeJSON(w, map[string]interface{}{"assignments": assignments})
	})))

	// 作业详情
	mux.Handle("GET /api/v1/teacher/assignments/{id}", authenticated(teacherOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		id := req.PathValue("id")
		a, err := r.assignmentService.GetAssignment(id)
		if err != nil {
			http.Error(w, err.Error(), http.StatusNotFound)
			return
		}
		writeJSON(w, map[string]interface{}{"assignment": a})
	}))))

	// 更新作业
	mux.Handle("POST /api/v1/teacher/assignments/{id}", authenticated(teacherOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		id := req.PathValue("id")
		var body struct {
			Title       string   `json:"title"`
			Description string   `json:"description"`
			QuestionIDs []string `json:"question_ids"`
		}
		if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		dueDate := time.Now().Add(7 * 24 * time.Hour)
		if err := r.assignmentService.Update(id, body.Title, body.Description, body.QuestionIDs, dueDate); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		writeJSON(w, map[string]interface{}{"status": "updated"})
	}))))

	// 作业状态变更
	mux.Handle("POST /api/v1/teacher/assignments/{id}/status", authenticated(teacherOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		id := req.PathValue("id")
		var body struct {
			Status string `json:"status"`
		}
		if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		if err := r.assignmentService.UpdateStatus(id, teacher.AssignmentStatus(body.Status)); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		writeJSON(w, map[string]interface{}{"status": "updated"})
	}))))

	// 删除作业
	mux.Handle("POST /api/v1/teacher/assignments/{id}/delete", authenticated(teacherOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		id := req.PathValue("id")
		if err := r.assignmentService.Delete(id); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		writeJSON(w, map[string]interface{}{"status": "deleted"})
	}))))
}

// setupAuthRoutes 认证路由 (注册/登录/刷新/登出)
func (r *Router) setupAuthRoutes(mux *http.ServeMux) {
	// 注册 (公开)
	mux.HandleFunc("POST /api/v1/auth/register", func(w http.ResponseWriter, req *http.Request) {
		var body struct {
			Email    string `json:"email"`
			Password string `json:"password"`
			Role     string `json:"role"`
			TenantID string `json:"tenant_id"`
		}
		if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
			http.Error(w, `{"error":"invalid request"}`, http.StatusBadRequest)
			return
		}
		if body.Email == "" || body.Password == "" {
			http.Error(w, `{"error":"email and password required"}`, http.StatusBadRequest)
			return
		}
		if body.Role == "" {
			body.Role = "student"
		}
		if body.TenantID == "" {
			body.TenantID = "default"
		}

		// 哈希密码
		hash, err := auth.HashPassword(body.Password)
		if err != nil {
			http.Error(w, `{"error":"failed to hash password"}`, http.StatusInternalServerError)
			return
		}

		// 创建用户
		user, err := r.userStore.CreateUser(body.Email, hash, auth.Role(body.Role), body.TenantID)
		if err != nil {
			http.Error(w, `{"error":"`+err.Error()+`"}`, http.StatusConflict)
			return
		}

		// 发布注册事件
		r.bus.Publish(eventbus.Event{
			Type: eventbus.UserRegistered, Source: "api",
			Data: map[string]interface{}{"user_id": user.ID, "email": user.Email},
		})

		writeJSON(w, map[string]interface{}{
			"user_id":    user.ID,
			"learner_id": user.LearnerID,
			"message":    "Registration successful. Please login.",
		})
	})

	// Admin 创建教师/管理员 (需 Admin 权限)
	mux.Handle("POST /api/v1/auth/register/staff", auth.AuthMiddleware(r.jwtSecret)(auth.RequireMinRole(auth.RoleAdmin)(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		var body struct {
			Email    string `json:"email"`
			Password string `json:"password"`
			Role     string `json:"role"`
			TenantID string `json:"tenant_id"`
		}
		if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
			http.Error(w, `{"error":"invalid request"}`, http.StatusBadRequest)
			return
		}
		if body.Email == "" || body.Password == "" {
			http.Error(w, `{"error":"email and password required"}`, http.StatusBadRequest)
			return
		}
		// 仅允许创建 teacher 或 admin
		if body.Role != "teacher" && body.Role != "admin" {
			http.Error(w, `{"error":"role must be teacher or admin"}`, http.StatusBadRequest)
			return
		}
		if body.TenantID == "" {
			body.TenantID = "default"
		}

		hash, err := auth.HashPassword(body.Password)
		if err != nil {
			http.Error(w, `{"error":"failed to hash password"}`, http.StatusInternalServerError)
			return
		}

		user, err := r.userStore.CreateUser(body.Email, hash, auth.Role(body.Role), body.TenantID)
		if err != nil {
			http.Error(w, `{"error":"`+err.Error()+`"}`, http.StatusConflict)
			return
		}

		r.bus.Publish(eventbus.Event{
			Type: eventbus.UserRegistered, Source: "api",
			Data: map[string]interface{}{"user_id": user.ID, "email": user.Email, "role": body.Role},
		})

		writeJSON(w, map[string]interface{}{
			"status":  "registered",
			"user_id": user.ID,
			"email":   user.Email,
			"role":    user.Role,
		})
	}))))

	// 登录 (公开)
	mux.HandleFunc("POST /api/v1/auth/login", func(w http.ResponseWriter, req *http.Request) {
		var body struct {
			Email    string `json:"email"`
			Password string `json:"password"`
		}
		if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
			http.Error(w, `{"error":"invalid request"}`, http.StatusBadRequest)
			return
		}

		// 验证凭据
		user, ok := r.userStore.Authenticate(body.Email, body.Password)
		if !ok {
			http.Error(w, `{"error":"invalid email or password"}`, http.StatusUnauthorized)
			return
		}

		// 生成 access token
		accessToken, err := auth.CreateAccessToken(r.jwtSecret, user.ID, user.Email, string(user.Role), user.TenantID, user.LearnerID)
		if err != nil {
			http.Error(w, `{"error":"failed to create token"}`, http.StatusInternalServerError)
			return
		}

		// 生成 refresh token (存储在 RefreshTokenStore)
		refreshToken, err := r.refreshStore.Create(user.ID, auth.DefaultRefreshDuration)
		if err != nil {
			http.Error(w, `{"error":"failed to create refresh token"}`, http.StatusInternalServerError)
			return
		}

		writeJSON(w, map[string]interface{}{
			"access_token":       accessToken,
			"refresh_token":      refreshToken,
			"token_type":         "bearer",
			"expires_in_seconds": int(auth.DefaultAccessDuration.Seconds()),
			"user": map[string]interface{}{
				"id":         user.ID,
				"email":      user.Email,
				"role":       user.Role,
				"learner_id": user.LearnerID,
				"tenant_id":  user.TenantID,
			},
		})
	})

	// 刷新 access token (公开,使用 refresh token)
	mux.HandleFunc("POST /api/v1/auth/refresh", func(w http.ResponseWriter, req *http.Request) {
		var body struct {
			RefreshToken string `json:"refresh_token"`
		}
		if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
			http.Error(w, `{"error":"invalid request"}`, http.StatusBadRequest)
			return
		}
		if body.RefreshToken == "" {
			http.Error(w, `{"error":"refresh_token required"}`, http.StatusBadRequest)
			return
		}

		// 轮换 refresh token
		newRefreshToken, userID, err := r.refreshStore.Rotate(body.RefreshToken)
		if err != nil {
			http.Error(w, `{"error":"`+err.Error()+`"}`, http.StatusUnauthorized)
			return
		}

		// 获取用户信息以签发新 access token
		user, ok := r.userStore.GetUser(userID)
		if !ok {
			http.Error(w, `{"error":"user not found"}`, http.StatusUnauthorized)
			return
		}

		accessToken, err := auth.CreateAccessToken(r.jwtSecret, user.ID, user.Email, string(user.Role), user.TenantID, user.LearnerID)
		if err != nil {
			http.Error(w, `{"error":"failed to create token"}`, http.StatusInternalServerError)
			return
		}

		writeJSON(w, map[string]interface{}{
			"access_token":       accessToken,
			"refresh_token":      newRefreshToken,
			"token_type":         "bearer",
			"expires_in_seconds": int(auth.DefaultAccessDuration.Seconds()),
			"user": map[string]interface{}{
				"id":         user.ID,
				"email":      user.Email,
				"role":       user.Role,
				"learner_id": user.LearnerID,
				"tenant_id":  user.TenantID,
			},
		})
	})

	// 登出 (撤销 refresh token)
	mux.HandleFunc("POST /api/v1/auth/logout", func(w http.ResponseWriter, req *http.Request) {
		var body struct {
			RefreshToken string `json:"refresh_token"`
		}
		if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
			http.Error(w, `{"error":"invalid request"}`, http.StatusBadRequest)
			return
		}
		if body.RefreshToken != "" {
			r.refreshStore.Revoke(body.RefreshToken)
		}
		writeJSON(w, map[string]interface{}{"status": "logged_out"})
	})

	// 当前用户信息 (需认证)
	mux.Handle("GET /api/v1/auth/me", auth.AuthMiddleware(r.jwtSecret)(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		user := auth.GetUserFromContext(req.Context())
		if user == nil {
			http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
			return
		}
		learnerID := user.LearnerID
		email := user.Email
		role := user.Role
		tenantID := user.TenantID
		if stored, ok := r.userStore.GetUser(user.ID); ok {
			learnerID = stored.LearnerID
			email = stored.Email
			role = stored.Role
			tenantID = stored.TenantID
		}
		writeJSON(w, map[string]interface{}{
			"id":         user.ID,
			"email":      email,
			"role":       role,
			"learner_id": learnerID,
			"tenant_id":  tenantID,
		})
	})))
}

// setupPrivacyRoutes 隐私合规路由
func (r *Router) setupPrivacyRoutes(mux *http.ServeMux, authenticated func(http.Handler) http.Handler) {
	// 获取同意状态
	mux.Handle("GET /api/v1/privacy/consent", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		user := auth.GetUserFromContext(req.Context())
		consentType := privacy.ConsentType(req.URL.Query().Get("type"))
		if consentType == "" {
			writeJSON(w, map[string]interface{}{"consents": r.privacyService.GetAllConsents(user.ID)})
			return
		}
		writeJSON(w, map[string]interface{}{"type": consentType, "granted": r.privacyService.GetConsent(user.ID, consentType)})
	})))

	// 设置同意
	mux.Handle("POST /api/v1/privacy/consent", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		var body struct {
			ConsentType string `json:"consent_type"`
			Granted     bool   `json:"granted"`
		}
		if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		user := auth.GetUserFromContext(req.Context())
		record := r.privacyService.RecordConsent(user.ID, privacy.ConsentType(body.ConsentType), body.Granted, req.RemoteAddr, req.UserAgent())
		r.bus.Publish(eventbus.Event{
			Type: eventbus.ConsentUpdated, Source: "api",
			Data: map[string]interface{}{"user_id": user.ID, "consent_type": body.ConsentType, "granted": body.Granted},
		})
		writeJSON(w, map[string]interface{}{"consent": record})
	})))

	// 请求数据导出
	mux.Handle("POST /api/v1/privacy/export", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		user := auth.GetUserFromContext(req.Context())
		job, err := r.privacyService.ExportUserData(user.ID)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		writeJSON(w, map[string]interface{}{"export": job})
	})))

	// 列出导出任务
	mux.Handle("GET /api/v1/privacy/export/jobs", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		user := auth.GetUserFromContext(req.Context())
		jobs := r.privacyService.GetExportJobs(user.ID)
		writeJSON(w, map[string]interface{}{"exports": jobs})
	})))

	// 请求账户删除
	mux.Handle("POST /api/v1/privacy/delete", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		var body struct {
			Reason string `json:"reason"`
		}
		json.NewDecoder(req.Body).Decode(&body)
		user := auth.GetUserFromContext(req.Context())
		request, err := r.privacyService.RequestDeletion(user.ID, body.Reason)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		writeJSON(w, map[string]interface{}{"deletion": request})
	})))

	// 获取删除状态
	mux.Handle("GET /api/v1/privacy/delete", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		user := auth.GetUserFromContext(req.Context())
		requests := r.privacyService.GetDeletionRequests(user.ID)
		writeJSON(w, map[string]interface{}{"deletions": requests})
	})))

	// 取消删除
	mux.Handle("POST /api/v1/privacy/delete/cancel", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		user := auth.GetUserFromContext(req.Context())
		if err := r.privacyService.CancelDeletion(user.ID); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		writeJSON(w, map[string]interface{}{"status": "cancelled"})
	})))
}

// setupAuditRoutes 审计日志路由
func (r *Router) setupAuditRoutes(mux *http.ServeMux, authenticated func(http.Handler) http.Handler) {
	adminOnly := auth.RequireMinRole(auth.RoleAdmin)

	// 获取审计日志
	mux.Handle("GET /api/v1/audit/logs", authenticated(adminOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		limit := 50
		logs := r.auditService.GetAllLogs(limit)
		writeJSON(w, map[string]interface{}{"logs": logs})
	}))))

	// 验证审计链
	mux.Handle("GET /api/v1/audit/verify", authenticated(adminOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		valid, brokenAt := r.auditService.VerifyChain()
		writeJSON(w, map[string]interface{}{"valid": valid, "broken_at": brokenAt})
	}))))
}

// setupTaskRoutes 任务调度路由
func (r *Router) setupTaskRoutes(mux *http.ServeMux, authenticated func(http.Handler) http.Handler) {
	adminOnly := auth.RequireMinRole(auth.RoleAdmin)

	// 列出任务 + 队列统计
	mux.Handle("GET /api/v1/admin/tasks", authenticated(adminOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		writeJSON(w, map[string]interface{}{
			"tasks":      r.taskQueue.ListRegisteredTasks(),
			"stats":      r.taskQueue.Stats(),
		})
	}))))

	// 执行历史
	mux.Handle("GET /api/v1/admin/tasks/history", authenticated(adminOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		writeJSON(w, map[string]interface{}{"history": r.taskQueue.GetHistory()})
	}))))

	// 手动触发任务
	mux.Handle("POST /api/v1/admin/tasks/trigger/{name}", authenticated(adminOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		name := req.PathValue("name")
		if err := r.taskQueue.Enqueue(scheduler.Task{Name: name}); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		writeJSON(w, map[string]interface{}{"status": "enqueued", "name": name})
	}))))

	// 队列统计
	mux.Handle("GET /api/v1/admin/tasks/queue/stats", authenticated(adminOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		writeJSON(w, map[string]interface{}{"stats": r.taskQueue.Stats()})
	}))))

	// 死信队列
	mux.Handle("GET /api/v1/admin/tasks/queue/dead-letters", authenticated(adminOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		writeJSON(w, map[string]interface{}{"dead_letters": r.taskQueue.GetDeadLetters()})
	}))))
}

// setupNotificationRoutes 通知路由
func (r *Router) setupNotificationRoutes(mux *http.ServeMux, authenticated func(http.Handler) http.Handler) {
	// 列出通知
	mux.Handle("GET /api/v1/notifications", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		user := auth.GetUserFromContext(req.Context())
		writeJSON(w, map[string]interface{}{"notifications": r.notificationSvc.GetAll(user.ID)})
	})))

	// 未读数量
	mux.Handle("GET /api/v1/notifications/unread-count", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		user := auth.GetUserFromContext(req.Context())
		unread := r.notificationSvc.GetUnread(user.ID)
		writeJSON(w, map[string]interface{}{"unread_count": len(unread)})
	})))

	// 全部标记已读
	mux.Handle("POST /api/v1/notifications/read-all", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		user := auth.GetUserFromContext(req.Context())
		r.notificationSvc.MarkAllRead(user.ID)
		writeJSON(w, map[string]interface{}{"status": "all_read"})
	})))

	// 单条标记已读
	mux.Handle("POST /api/v1/notifications/{id}/read", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		id := req.PathValue("id")
		if err := r.notificationSvc.MarkRead(id); err != nil {
			http.Error(w, err.Error(), http.StatusNotFound)
			return
		}
		writeJSON(w, map[string]interface{}{"status": "read"})
	})))

	// 获取偏好
	mux.Handle("GET /api/v1/notifications/preferences", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		user := auth.GetUserFromContext(req.Context())
		writeJSON(w, map[string]interface{}{"preferences": r.notificationSvc.GetPreference(user.ID)})
	})))

	// 设置偏好
	mux.Handle("POST /api/v1/notifications/preferences", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		var pref notification.NotificationPreference
		if err := json.NewDecoder(req.Body).Decode(&pref); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		user := auth.GetUserFromContext(req.Context())
		pref.UserID = user.ID
		r.notificationSvc.SetPreference(pref)
		writeJSON(w, map[string]interface{}{"status": "updated", "preferences": pref})
	})))
}

// setupTenantRoutes 租户管理路由
func (r *Router) setupTenantRoutes(mux *http.ServeMux, authenticated func(http.Handler) http.Handler) {
	adminOnly := auth.RequireMinRole(auth.RoleAdmin)

	// 创建租户
	mux.Handle("POST /api/v1/tenants", authenticated(adminOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		var body struct {
			Name string `json:"name"`
			Slug string `json:"slug"`
			Plan string `json:"plan"`
		}
		if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		t, err := r.tenantService.CreateTenant(body.Name, body.Slug, body.Plan)
		if err != nil {
			http.Error(w, err.Error(), http.StatusConflict)
			return
		}
		writeJSON(w, map[string]interface{}{"tenant": t})
	}))))

	// 列出租户
	mux.Handle("GET /api/v1/tenants", authenticated(adminOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		writeJSON(w, map[string]interface{}{"tenants": r.tenantService.ListTenants()})
	}))))

	// 租户详情
	mux.Handle("GET /api/v1/tenants/{id}", authenticated(adminOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		id := req.PathValue("id")
		t, err := r.tenantService.GetTenant(id)
		if err != nil {
			http.Error(w, err.Error(), http.StatusNotFound)
			return
		}
		quota, _ := r.tenantService.GetQuota(id)
		writeJSON(w, map[string]interface{}{"tenant": t, "quota": quota})
	}))))

	// 更新租户
	mux.Handle("POST /api/v1/tenants/{id}", authenticated(adminOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		id := req.PathValue("id")
		var body struct {
			Name string `json:"name"`
			Plan string `json:"plan"`
		}
		if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		if err := r.tenantService.UpdateTenant(id, body.Name, body.Plan); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		writeJSON(w, map[string]interface{}{"status": "updated"})
	}))))

	// 删除租户
	mux.Handle("POST /api/v1/tenants/{id}/delete", authenticated(adminOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		id := req.PathValue("id")
		if err := r.tenantService.DeleteTenant(id); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		writeJSON(w, map[string]interface{}{"status": "deleted"})
	}))))

	// 更新配额
	mux.Handle("POST /api/v1/tenants/{id}/quota", authenticated(adminOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		id := req.PathValue("id")
		var body struct {
			MaxUsers     int `json:"max_users"`
			MaxLLMTokens int `json:"max_llm_tokens"`
		}
		if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		if err := r.tenantService.UpdateQuota(id, body.MaxUsers, body.MaxLLMTokens); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		writeJSON(w, map[string]interface{}{"status": "updated"})
	}))))

	// 重置配额
	mux.Handle("POST /api/v1/tenants/{id}/quota/reset", authenticated(adminOnly(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		id := req.PathValue("id")
		if err := r.tenantService.ResetQuota(id); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		writeJSON(w, map[string]interface{}{"status": "reset"})
	}))))
}

// setupLearnerRoutes 学习者路由
func (r *Router) setupLearnerRoutes(mux *http.ServeMux, authenticated func(http.Handler) http.Handler) {
	// 学习进度
	mux.Handle("GET /api/v1/progress/{learnerID}", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		learnerID := req.PathValue("learnerID")
		progress := r.assessment.GetProgress(learnerID)
		writeJSON(w, map[string]interface{}{"progress": progress})
	})))

	// 知识图谱
	mux.Handle("GET /api/v1/knowledge-graph", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		graph := model.BuildSampleMathGraph()
		writeJSON(w, map[string]interface{}{
			"nodes": graph.Nodes,
			"order": graph.TopologicalSort(),
		})
	})))
}

func writeJSON(w http.ResponseWriter, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(data)
}

func generateShortID() string {
	return time.Now().Format("20060102150405")
}

// setupVisionRoutes 对齐 Python POST /api/v1/vision/analyze
func (r *Router) setupVisionRoutes(mux *http.ServeMux, authenticated func(http.Handler) http.Handler) {
	mux.Handle("POST /api/v1/vision/analyze", authenticated(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		var body struct {
			Images         []string `json:"images"`
			KnowledgeID    string   `json:"knowledge_id"`
			LearnerMessage string   `json:"learner_message"`
			Level          string   `json:"level"`
			Mastery        float64  `json:"mastery"`
		}
		if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		if len(body.Images) == 0 || len(body.Images) > 4 {
			http.Error(w, "images must contain 1-4 items", http.StatusBadRequest)
			return
		}
		if body.KnowledgeID == "" {
			body.KnowledgeID = "general"
		}
		if body.Level == "" {
			body.Level = "beginner"
		}
		question := body.LearnerMessage
		if question == "" {
			question = "请分析这张与「" + body.KnowledgeID + "」相关的图片"
		}

		img := body.Images[0]
		mimeType := "image/png"
		if mt, _, err := r.visionService.ValidateDataURL(img); err == nil {
			mimeType = mt
		} else if err := r.visionService.ValidateImageURL(img); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		respText, meta, err := r.visionService.AnalyzeImage(img, mimeType, question)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}
		if meta == nil {
			meta = map[string]interface{}{}
		}
		meta["image_count"] = len(body.Images)
		meta["knowledge_id"] = body.KnowledgeID
		meta["level"] = body.Level
		meta["mastery"] = body.Mastery

		writeJSON(w, map[string]interface{}{
			"success": true,
			"data": map[string]interface{}{
				"response": respText,
				"metadata": meta,
			},
		})
	})))
}
