# 京东云 CVM 部署手册

这套配置选择“单台 CVM + Docker Compose”作为第一版：成本和概念数量可控，同时保留 API、Worker、MCP、PostgreSQL、Redis 的真实服务边界。流量增长后，可把镜像迁移到京东云 Kubernetes，把数据库和 Redis 切到托管服务，应用接口不需要改变。

## 1. 准备 CVM

建议使用 Ubuntu 22.04/24.04、至少 4 vCPU、8 GB RAM 和 80 GB SSD。安全组只向公网开放 `22`、`80`、`443`；PostgreSQL、Redis、MCP 与 API 不直接暴露公网。给 CVM 绑定弹性公网 IP，并把域名 A 记录指向该地址。

安装 Docker Engine 和 Compose Plugin 后，将项目同步到 `/opt/business-english-coach`。复制 `.env.example` 为 `.env`，至少替换：

- `APP_ENV=production`
- 长度不少于 32 字符的随机 `SECRET_KEY`
- PostgreSQL 强密码及匹配的 `DATABASE_URL`
- 真实模型需要的 `AI_PROVIDER`、`AI_API_KEY`、`AI_BASE_URL`
- 正式域名对应的 `CORS_ORIGINS`

不要把 `.env`、数据库备份、上传资料或语音文件提交到代码仓库或制作进镜像。

## 2. 首次发布

```bash
chmod +x deploy/jdcloud/deploy.sh
./deploy/jdcloud/deploy.sh /opt/business-english-coach
curl http://127.0.0.1/api/health
```

脚本先校验 Compose、构建镜像、执行 Alembic，再原地更新服务；它不会删除卷。首次确认 HTTP 正常后，使用 Certbot 或已有证书配置 443，并将 80 重定向到 HTTPS。

## 3. 备份、升级与回滚

发布前执行带时间戳的 `pg_dump`，把加密备份同步到京东云对象存储，并定期实际演练恢复。上传卷也应单独备份。升级使用新的镜像 tag，执行迁移后滚动重建容器。应用回滚切回前一镜像；本项目的 Alembic downgrade 故意不删除表，破坏性 schema 回滚必须经过人工审批和独立恢复方案。

## 4. 运行检查

- `/api/health`：API 与数据库连通性。
- `/metrics`：Agent 成功/失败、节点延迟、Token 与工具调用计数。
- `docker compose logs api worker mcp`：结构化服务日志。
- 数据库中 `agent_runs` 与 `trace_events`：逐次运行的可审计轨迹。
- 告警建议：5 分钟失败率、p95 延迟、队列积压、磁盘、数据库连接数和证书过期时间。
