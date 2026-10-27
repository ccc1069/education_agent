# ============================================================
# 多Agent智能教育系统 - Java/Spring Boot 后端
# 多阶段构建: builder(Maven 打包) + runtime(JRE 21 精简)
# ============================================================

# ---- builder ----
FROM maven:3.9-eclipse-temurin-21-alpine AS builder

WORKDIR /build

# 依赖缓存层 (利用 Docker 层缓存加速后续构建)
COPY pom.xml .
RUN mvn dependency:go-offline -B

# 源码 + 打包
COPY src/ ./src/
RUN mvn clean package -DskipTests -B \
    && mv target/*.jar app.jar \
    && java -Djarmode=layertools -jar app.jar extract

# ---- runtime ----
FROM eclipse-temurin:21-jre-alpine AS runtime

RUN apk add --no-cache curl tzdata \
    && addgroup -S appgroup && adduser -S appuser -G appgroup

WORKDIR /app

# 分层 JAR: 按变更频率分层,最大化 Docker 缓存命中率
COPY --from=builder /build/dependencies/ ./
COPY --from=builder /build/spring-boot-loader/ ./
COPY --from=builder /build/snapshot-dependencies/ ./
COPY --from=builder /build/application/ ./

USER appuser:appuser

# 元数据
LABEL org.opencontainers.image.title="multi-agent-education-java" \
      org.opencontainers.image.description="Multi-Agent Intelligent Education System - Java/Spring Boot Backend" \
      org.opencontainers.image.version="2.0.0" \
      org.opencontainers.image.source="https://github.com/example/multi-agent-education"

EXPOSE 8080

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8080/actuator/health || exit 1

# Spring Boot 分层启动 + JVM 容器感知
ENTRYPOINT ["java", \
    "-XX:+UseContainerSupport", \
    "-XX:MaxRAMPercentage=75.0", \
    "-Djava.security.egd=file:/dev/./urandom", \
    "org.springframework.boot.loader.launch.JarLauncher"]
