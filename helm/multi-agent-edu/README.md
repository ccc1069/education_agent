# multi-agent-edu Helm Chart

Kubernetes 生产部署 chart,适用于 EKS / ACK / 自建 K8s 集群。

## 前置依赖

- Kubernetes 1.24+
- Helm 3.10+
- nginx-ingress-controller
- cert-manager(用于 TLS 自动签发)
- kube-prometheus-stack(用于监控指标抓取)
- Bitnami Helm repo(`helm repo add bitnami https://charts.bitnami.com/bitnami`)

## 快速安装

```sh
# 1. 拉取依赖 chart
helm dependency update

# 2. 创建命名空间
kubectl create namespace edu-prod

# 3. 准备生产密钥(用 Sealed Secrets 或 kubectl create secret)
#    推荐: 用 external-secrets 从 Vault/AWS Secrets Manager 拉取
kubectl -n edu-prod create secret generic multi-agent-edu-secret \
  --from-literal=DATABASE_URL='postgresql+asyncpg://...' \
  --from-literal=JWT_SECRET_KEY='...' \
  --from-literal=OPENAI_API_KEY='...' \
  --from-literal=ENCRYPTION_KEY='...'

# 4. 安装(dev/本地集群)
helm install edu ./multi-agent-edu -n edu-prod

# 5. 安装(生产)
helm install edu ./multi-agent-edu -n edu-prod -f values-prod.yaml
```

## 关键资源

| 资源 | 说明 |
|------|------|
| Deployment | 3 副本(生产 5),RollingUpdate(maxSurge=1, maxUnavailable=0) |
| HPA | CPU 70%(生产 65%),3-20(生产 5-50) |
| Service | ClusterIP:8000 |
| Ingress | nginx + TLS(cert-manager) |
| ConfigMap | 非敏感配置(checksum 触发滚动更新) |
| Secret | 敏感配置(生产用 Sealed Secrets) |
| PDB | minAvailable=1(生产 2),保证滚动更新不丢容量 |
| NetworkPolicy | 零信任:仅允许 ingress-nginx/monitoring/同 chart 内流量 |
| ServiceMonitor | Prometheus 抓取 /metrics(15s 间隔) |
| InitContainer | 启动前跑 `alembic upgrade head` |

## 滚动更新

```sh
# 改 image.tag 后
helm upgrade edu ./multi-agent-edu -n edu-prod -f values-prod.yaml

# 监控滚动状态
kubectl -n edu-prod rollout status deploy/edu
```

## 回滚

```sh
helm history edu -n edu-prod
helm rollback edu <REVISION> -n edu-prod
```

## 验证

```sh
# 健康检查
kubectl -n edu-prod port-forward svc/edu 8000:8000
curl http://localhost:8000/health
curl http://localhost:8000/ready

# 指标
curl http://localhost:8000/metrics

# 迁移日志
kubectl -n edu-prod logs deploy/edu -c migrator
```

## 生产化清单

- [ ] values-prod.yaml 中所有 `REPLACE_WITH_SEALED_SECRET` 已替换为 Sealed Secret
- [ ] 存储 StorageClass 已配置(`fast-ssd`)
- [ ] PostgreSQL HA(主从)启用 `architecture: replication`
- [ ] Redis HA 启用 `architecture: replication`
- [ ] 跨可用区反亲和启用(`topology.kubernetes.io/zone`)
- [ ] Ingress 域名 + TLS 证书已配置
- [ ] Prometheus ServiceMonitor 已发现
- [ ] 日志聚合(Fluent Bit / Loki)接入

## 配置说明

| 参数 | 默认 | 说明 |
|------|------|------|
| `image.repository` | `multi-agent-edu/python-api` | 镜像仓库 |
| `image.tag` | `2.0.0` | 镜像 tag |
| `replicaCount` | `3` | 副本数(HPA 启用后为下限) |
| `resources.requests.cpu` | `250m` | CPU 请求 |
| `resources.limits.cpu` | `1000m` | CPU 上限 |
| `autoscaling.minReplicas` | `3` | HPA 最小副本 |
| `autoscaling.maxReplicas` | `20` | HPA 最大副本 |
| `autoscaling.targetCPUUtilizationPercentage` | `70` | HPA 目标 CPU |
| `probe.liveness.initialDelaySeconds` | `30` | 启动后等待时间 |
| `ingress.hosts[0].host` | `api.edu.local` | 域名 |
| `pdb.minAvailable` | `1` | PDB 最小可用 |
| `networkPolicy.enabled` | `true` | 启用 NetworkPolicy |
| `migrator.enabled` | `true` | 启动前跑迁移 |
| `postgresql.architecture` | `standalone` | 生产用 `replication` |
| `redis.architecture` | `standalone` | 生产用 `replication` |
