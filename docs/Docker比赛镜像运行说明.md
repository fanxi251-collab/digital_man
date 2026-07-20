# LingJing AI 比赛 Docker 镜像运行说明

当前时间：2026-07-20 11:53 +08:00（Asia/Shanghai）

## 1. 交付物

比赛镜像归档：

```text
lingjing-ai-competition-amd64.tar
```

目标平台为 Linux/amd64。运行电脑需要安装 Docker Desktop 或 Docker Engine，并允许访问阿里云百炼和高德的 HTTPS/WSS 服务。

镜像已内置构建时的知识文档、Qdrant 向量库、景点、美食、反馈、会话和游客分析数据。真实 API Key 不在镜像中。

## 2. 校验并导入镜像

Windows PowerShell：

```powershell
Get-FileHash ".\lingjing-ai-competition-amd64.tar" -Algorithm SHA256
docker load -i ".\lingjing-ai-competition-amd64.tar"
docker image inspect lingjing-ai:competition `
  --format "{{.Id}} {{.Os}}/{{.Architecture}}"
```

Linux/macOS：

```bash
sha256sum ./lingjing-ai-competition-amd64.tar
docker load -i ./lingjing-ai-competition-amd64.tar
docker image inspect lingjing-ai:competition \
  --format '{{.Id}} {{.Os}}/{{.Architecture}}'
```

镜像平台应显示 `linux/amd64`。

## 3. 准备运行配置

在镜像归档旁新建 `competition.env`，内容如下：

```dotenv
LJAPI_KEY=替换为阿里云百炼API_Key
MAP_API=替换为高德Web服务Key
MAP_JS_API=替换为高德JS_API_Key
MAP_JS_SECURITY_CODE=替换为高德JS安全密钥

REDIS_ENABLED=false
KG_ENABLED=false
AGENT_EXECUTOR_MODE=langgraph
LJ_LLM_MODEL=qwen3.7-max
LJ_EMBEDDING_MODEL=text-embedding-v4
LJ_EMBEDDING_DIMENSIONS=1024
LJ_REALTIME_MODEL=qwen-audio-3.0-realtime-flash
```

不要把填写真实密钥后的 `competition.env` 上传到公共平台或提交到 Git。

## 4. 启动

Windows PowerShell：

```powershell
docker run --name lingjing-ai-competition `
  --env-file ".\competition.env" `
  -p 8000:8000 `
  -d `
  lingjing-ai:competition
```

Linux/macOS：

```bash
docker run --name lingjing-ai-competition \
  --env-file ./competition.env \
  -p 8000:8000 \
  -d \
  lingjing-ai:competition
```

查看状态和日志：

```powershell
docker ps --filter "name=lingjing-ai-competition"
docker logs --tail 100 lingjing-ai-competition
```

健康状态变为 `healthy` 后访问：

| 功能 | 地址 |
| --- | --- |
| 游客端 | `http://127.0.0.1:8000/visitor` |
| AI 导游 | `http://127.0.0.1:8000/visitor/guide` |
| 景点探索 | `http://127.0.0.1:8000/visitor/explore` |
| 互动地图 | `http://127.0.0.1:8000/visitor/map` |
| 美食推荐 | `http://127.0.0.1:8000/visitor/food` |
| 游客反馈 | `http://127.0.0.1:8000/visitor/feedback` |
| 资料管理 | `http://127.0.0.1:8000/admin/documents` |
| 景点管理 | `http://127.0.0.1:8000/admin/attractions` |
| 美食管理 | `http://127.0.0.1:8000/admin/foods` |
| 反馈管理 | `http://127.0.0.1:8000/admin/feedback` |
| 游客分析 | `http://127.0.0.1:8000/admin/analytics` |
| OpenAPI | `http://127.0.0.1:8000/docs` |

## 5. 停止和再次启动

```powershell
docker stop lingjing-ai-competition
docker start lingjing-ai-competition
```

容器未被删除时，运行期间新增的数据会保留在该容器的可写层。

## 6. 使用命名卷长期保存数据

需要在重新创建容器后仍保留上传资料、会话、景点、美食和反馈时，可首次启动就挂载命名卷：

```powershell
docker run --name lingjing-ai-competition `
  --env-file ".\competition.env" `
  -p 8000:8000 `
  -v lingjing-data:/app/data `
  -v lingjing-qdrant:/app/qdrant_db `
  -d `
  lingjing-ai:competition
```

新命名卷首次挂载时会使用镜像内演示数据初始化。不要让多个容器同时写入同一个 `lingjing-qdrant` 卷。

## 7. 不提供第三方密钥时

没有 `LJAPI_KEY` 或高德 Key 时，容器仍可启动并展示内置页面、景点、美食、反馈和资料；完整 LLM 问答、实时数字人语音、天气、路线和地图能力会不可用或降级。

## 8. 常见问题

### 容器一直不是 healthy

```powershell
docker logs --tail 200 lingjing-ai-competition
```

重点检查 Qdrant 是否被另一个容器占用、应用是否从 `/app` 启动，以及 8000 端口是否已被宿主机其他程序占用。

### 8000 端口已占用

把宿主机端口改为 8080：

```powershell
docker run --name lingjing-ai-competition `
  --env-file ".\competition.env" `
  -p 8080:8000 `
  -d `
  lingjing-ai:competition
```

访问地址相应改为 `http://127.0.0.1:8080/visitor`。

### 数字人不能使用麦克风

本机 `127.0.0.1` 可以使用 HTTP。若部署到其他电脑或公网域名，浏览器麦克风和 WebSocket 应通过 HTTPS/WSS 访问。

### 管理端安全

当前管理端没有账号鉴权。比赛演示建议仅在本机或可信局域网开放，不要直接暴露到公网。
