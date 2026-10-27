# ============================================================
# 多Agent智能教育系统 - Go 后端
# 多阶段构建: builder(编译) + distroless(精简运行时)
# ============================================================

# ---- builder ----
FROM golang:1.25-alpine AS builder

WORKDIR /build

# 安装 git (go mod 可能需要)
RUN apk add --no-cache git ca-certificates tzdata

# 依赖缓存层
COPY go.mod go.sum ./
RUN go mod download && go mod verify

# 源码
COPY cmd/ ./cmd/
COPY internal/ ./internal/

# 编译: 静态链接 + 剥离符号 + 禁用 CGO
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
    -ldflags='-w -s -extldflags "-static"' \
    -a -installsuffix cgo \
    -o /build/server \
    ./cmd/main.go

# ---- runtime (distroless with shell for healthcheck) ----
# 使用 debug 变体: 包含 busybox shell + wget,支持 HEALTHCHECK
FROM gcr.io/distroless/static-debian12:debug

WORKDIR /app

# 从 builder 拷贝时区数据 + 证书 + 二进制
COPY --from=builder /usr/share/zoneinfo /usr/share/zoneinfo
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=builder /build/server /app/server

# distroless 已预设 nonroot 用户 (uid=65532)
USER nonroot:nonroot

# 元数据
LABEL org.opencontainers.image.title="multi-agent-education-go" \
      org.opencontainers.image.description="Multi-Agent Intelligent Education System - Go Backend" \
      org.opencontainers.image.version="2.0.0" \
      org.opencontainers.image.source="https://github.com/example/multi-agent-education"

EXPOSE 8081

# 健康检查 (distroless debug 变体包含 wget)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["/usr/bin/wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:8081/health"] || exit 1

ENTRYPOINT ["/app/server"]
