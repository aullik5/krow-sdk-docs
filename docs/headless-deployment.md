# Krow Agent SDK Headless 部署指南（容器 / 服务端）

> **当前状态（2026-05-21）** ✅：自 `krow-agent-sdk 0.8.12.15` 起，headless（无桌面 IDE）
> 场景下 `pip install krow-agent-sdk` + `KROW_API_KEY` 即可装上即跑——**无需** mock
> `app.container`、**无需** root 权限、**无需**写 `site-packages/`。
>
> 本文档覆盖 KrowChat 等外部团队最常用的两种部署形态：
>
> 1. **基于 `python:slim` 自建容器**（推荐 — 完全自主控制 base image / Python 版本 / 依赖）
> 2. **基于官方 `ghcr.io/aullik5/krow-headless` 镜像扩展**（最快 — 不操心 system libs）
>
> 前置阅读：[`quickstart.md`](./quickstart.md)（5 分钟上手 SDK API）
> · [`runtime-install.md`](./runtime-install.md)（拉私有 runtime wheel）

---

## 0. 这份文档适合谁？

| 场景 | 是否适用 |
|---|---|
| 在 K8s Pod 里跑 SDK 服务端（KrowChat / 内部 agent 平台） | ✅ |
| Docker container 跑离线批处理 agent 任务 | ✅ |
| FastAPI / Flask / gRPC 后端在每个请求里 `agent.run(...)` | ✅ |
| CI/CD pipeline 触发 agent 任务（GitHub Actions / Argo / Tekton） | ✅ |
| 桌面 IDE / 端用户机器跑 agent | ❌（用 Krow 桌面 app 而非本指南） |
| Nuitka 打包成单文件 desktop binary | ❌（走 `scripts/build_portable.py`，不在 SDK 范围） |

---

## 1. 三种部署形态对比

| 形态 | base image | 镜像大小 | 控制粒度 | 适合 |
|---|---|---|---|---|
| **A. python:slim 自建** | `python:3.13-slim` | ~250-400 MB | 全部自主 | KrowChat 类——已有自己的服务镜像规范 |
| **B. 官方 headless 镜像扩展** | `ghcr.io/aullik5/krow-headless:latest` | ~700 MB | base 由 Krow 维护 | 想最快跑通、不想操心 system libs |
| **C. 现有 ML 镜像 + pip 加装** | e.g. `pytorch/pytorch:*` | ~3-5 GB | 与现有训练栈共存 | 已有 ML 平台想加 agent 能力 |

下文 §2、§3、§4 分别给出可直接复制的 Dockerfile。

---

## 2. 形态 A：基于 `python:slim` 自建（推荐 — KrowChat 类场景）

### 2.1 最小可用 Dockerfile（**直接复制即可跑**）

```dockerfile
# syntax=docker/dockerfile:1.6
FROM python:3.13-slim

# Step 1: system libs + 非 root 用户（合并到单一 RUN 层，避免多层 dpkg-divert 瞬态 bug）
# 注：见 §6 Q3 的故障排查（这是踩过坑的反模式：分多个 RUN 装会偶发 /bin/sh 被损坏）
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 krow \
    && mkdir -p /home/krow/data \
    && chown krow:krow /home/krow/data

USER krow
WORKDIR /home/krow

# Step 2: pip install SDK（合并到单一 RUN 层；同样为避免 multi-RUN 瞬态 bug）
# 注：[all] extras 包含 office/knowledge/remote/visual；按需可缩为 [office] 等
RUN pip install --user --no-cache-dir "krow-agent-sdk[all]==0.8.12.15"

# Step 3: 一等公民环境变量（0.8.12.15 起 SDK 直接读 KROW_DATA_DIR）
ENV PATH="/home/krow/.local/bin:$PATH" \
    KROW_DATA_DIR=/home/krow/data \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Step 4: 你的应用代码
COPY --chown=krow:krow my_app/ /home/krow/my_app/

# tini 作为 PID 1，正确传递 SIGTERM + 回收 zombie 进程
ENTRYPOINT ["tini", "--"]
CMD ["python", "-m", "my_app"]
```

构建 + 跑：

```bash
docker build -t my-krow-agent:0.1 .
docker run --rm -e KROW_API_KEY=sk-user-xxxxx my-krow-agent:0.1
```

### 2.2 按场景裁剪 extras

`[all]` 包含全部能力，体积最大；若只用部分功能可缩：

| extras | 引入的能力 | 典型大小（增量） |
|---|---|---|
| 无（核心） | Agent ReACT 核心、协议、LLM 调用 | ~30 MB |
| `[office]` | docx / pptx / xlsx / pdf / 图像 | +180 MB |
| `[knowledge]` | networkx / jieba 等知识图谱 | +20 MB |
| `[remote]` | fastapi / uvicorn / websockets 接前端 SSE | +40 MB |
| `[visual]` | cairosvg / cairocffi 等视觉质检 | +30 MB（**需 §2.4 system libs**） |
| `[all]` | 上述全部 | ~270 MB |

### 2.3 必需 / 推荐环境变量

| 变量 | 来源 | 必填 | 用途 |
|---|---|---|---|
| `KROW_API_KEY` | **应用层读** → 显式传 `AgentBuilder.with_krow_api_key(...)` | ✅ | Krow Cloud 鉴权 token |
| `KROW_DATA_DIR` | **SDK 自动读** (`modules/utils/portable_path.py` 0.8.12.15+) | 推荐 | 显式指定可写数据目录；不设则按 XDG / `~/Library/Application Support` / `%APPDATA%` 回退 |
| `KROW_BASE_URL` | **应用层读** → 显式传 `AgentBuilder.with_base_url(...)` | 可选 | 自定义 Cloud endpoint（staging / 私有化部署） |
| `PYTHONUNBUFFERED=1` | Python runtime | 推荐 | 容器内日志即时输出 |

> ⚠️ **注意区分**：`KROW_API_KEY` / `KROW_BASE_URL` 是 **cookbook convention**，**SDK 不会自动读** —— 你的入口代码需要 `os.environ.get(...)` 后显式传给 `AgentBuilder`。**只有** `KROW_DATA_DIR` 是 SDK 直接消费的。完整 SSOT 参 `modules/utils/portable_path.py:ENV_KROW_DATA_DIR`。

入口代码示例：

```python
import os
from krow_agent_sdk import AgentBuilder

agent = (
    AgentBuilder()
    .with_krow_api_key(os.environ["KROW_API_KEY"])
    .with_project_root(os.environ.get("KROW_PROJECT_ROOT", "/home/krow/workspace"))
    .build()
)
result = agent.run("...")
agent.shutdown()
```

### 2.4 启用视觉质检需要的 system libs（仅 `[visual]` / `[all]` 用户）

`cairosvg` / `cairocffi` 依赖 cairo + pango + CJK 字体（SVG `<text>` 渲染）。如果你装了
`[visual]` 或 `[all]`，在 Step 1 的 `apt-get install` 段追加：

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        tini \
        libcairo2 \
        libpango-1.0-0 libpangocairo-1.0-0 libpangoft2-1.0-0 \
        fonts-noto-cjk \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 krow \
    && mkdir -p /home/krow/data \
    && chown krow:krow /home/krow/data
```

否则视觉质检调用会报 `OSError: cannot load library 'libpango-1.0.so.0'`（详 §6 Q7）。

---

## 3. 形态 B：基于官方 headless 镜像扩展（最快）

如果你不想自己装 system libs、不在乎 ~700 MB 镜像、且 base 锁 Python 3.11 可接受：

```dockerfile
FROM ghcr.io/aullik5/krow-headless:latest

# 官方镜像已配：USER krow (UID 1000) / cairo / 字体 / tini / [headless,sdk] 全套
# 你只需 COPY 你的应用代码 + 设入口
COPY --chown=krow:krow my_app/ /home/krow/my_app/
ENV KROW_API_KEY=sk-user-...
CMD ["python", "-m", "my_app"]
```

> 官方镜像里 `krow_agent_sdk` 顶级包已 `pip install` 到位（PR-2a, 2026-05-13）；外部团队直接
> `from krow_agent_sdk import AgentBuilder` 即可。镜像 SSOT：`deploy/Dockerfile.headless`。

**何时不用 B 而用 A**：

- 需要 Python 3.12 / 3.13（B 当前锁 3.11）
- 镜像必须 < 500 MB（B 当前 ~700 MB）
- 公司有自己的 base image 标准 / 安全扫描白名单（B 的 base 是 Krow 维护的）

---

## 4. 形态 C：在现有 ML 镜像上加装 SDK

适合：你已经有 `pytorch/pytorch:2.x-cuda12-runtime` 之类的 base 镜像跑 ML 训练 / inference，想给同一容器加上 agent 能力。

```dockerfile
FROM pytorch/pytorch:2.4.0-cuda12.4-cudnn9-runtime

# 注：pytorch 镜像默认 root；如要切非 root 自己加 useradd
RUN pip install --no-cache-dir "krow-agent-sdk[office]==0.8.12.15"

ENV KROW_DATA_DIR=/workspace/krow_data
# ...
```

注意事项：

1. 大概率不需要 `[visual]`（ML 镜像通常已含 GPU + CUDA，不跑 cairo SVG 渲染）
2. PyTorch 镜像默认 root；按你的安全规范加 `useradd` + `USER` 切非 root
3. SDK + ML 框架可能争 numpy / pandas / Pillow 版本——建议用 `pip install --constraint` 锁版本

---

## 5. Kubernetes 部署最佳实践

### 5.1 Deployment 完整示例（PodSecurity Admission `restricted` 兼容）

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: krow-agent-worker
  labels:
    app: krow-agent-worker
spec:
  replicas: 3
  selector:
    matchLabels:
      app: krow-agent-worker
  template:
    metadata:
      labels:
        app: krow-agent-worker
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        runAsGroup: 1000
        fsGroup: 1000
        seccompProfile:
          type: RuntimeDefault
      containers:
      - name: agent
        image: your-registry/krow-agent-app:0.1
        imagePullPolicy: IfNotPresent
        env:
        - name: KROW_API_KEY
          valueFrom:
            secretKeyRef:
              name: krow-credentials
              key: api-key
        - name: KROW_DATA_DIR
          value: /data/krow
        - name: PYTHONUNBUFFERED
          value: "1"
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities:
            drop: ["ALL"]
        volumeMounts:
        - name: krow-data
          mountPath: /data/krow
        - name: tmp
          mountPath: /tmp
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
        startupProbe:
          exec:
            command: ["python", "-c", "import krow_agent_sdk; print('ok')"]
          failureThreshold: 30
          periodSeconds: 10
        livenessProbe:
          exec:
            command: ["python", "-c", "import krow_agent_sdk; print('ok')"]
          periodSeconds: 30
          timeoutSeconds: 10
      volumes:
      - name: krow-data
        emptyDir:
          sizeLimit: 1Gi
      - name: tmp
        emptyDir: {}
---
apiVersion: v1
kind: Secret
metadata:
  name: krow-credentials
type: Opaque
stringData:
  api-key: sk-user-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

注意：

- `securityContext.runAsNonRoot: true` + `runAsUser: 1000` 必须与 Dockerfile 里的 `useradd -u 1000` 一致
- `readOnlyRootFilesystem: true` + `emptyDir` mount 在 `KROW_DATA_DIR` 是 PodSecurityAdmission `restricted` 兼容的关键
- `startupProbe.failureThreshold: 30 × 10s = 5min` 给 SDK 首次加载 ACT yaml + ToolManager 留够时间
- `livenessProbe` 只做最轻量的 import 检测；**不要**把 `agent.run(...)` 当 liveness 探针（agent 任务可能 30s-数分钟）

### 5.2 SIGTERM 优雅关闭

`agent.run()` 是阻塞同步调用。容器收到 SIGTERM 后，业务层应：

```python
import signal
from krow_agent_sdk import AgentBuilder

agent = AgentBuilder().with_krow_api_key(...).build()
shutting_down = False

def _on_sigterm(signum, frame):
    global shutting_down
    shutting_down = True

signal.signal(signal.SIGTERM, _on_sigterm)

try:
    while not shutting_down:
        task = your_queue.pop()
        if task:
            result = agent.run(task)
            your_queue.ack(result)
finally:
    agent.shutdown()
```

要点：

- 让当前 in-flight `agent.run(...)` 完成（不要中途 kill —— LLM token 已扣，半成品无价值）
- 设标志位让 worker loop 不再接新任务
- 最后调 `agent.shutdown()` 释放 EventBus / FileWatcher / 后台线程

K8s 配 `terminationGracePeriodSeconds`：

```yaml
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 300  # 给 LLM 任务最多 5 分钟收尾
```

### 5.3 PodSecurityAdmission `restricted` 兼容性 checklist

SDK 0.8.12.15+ 通过 PSA `restricted`：

- ✅ 不需要 root（Dockerfile `USER 1000`）
- ✅ 不需要 `hostPath` mount（用 `emptyDir` / `PVC`）
- ✅ 不需要 `privileged: true` / 任何 `capabilities.add`
- ✅ 可配 `readOnlyRootFilesystem: true`（`KROW_DATA_DIR` 走 mount volume）
- ✅ 不需要 host network / host PID / host IPC
- ✅ 不需要 `allowPrivilegeEscalation`

---

## 6. 常见故障排查

### Q1: `build()` 报 "LLM provider 不可用" / `LLMProviderUnavailableError`

**根因**：在 0.8.12.14 及以前，SDK `_ensure_ai_manager` 硬依赖 `app.container` 模块（IDE
运行时的内部模块），headless 场景下静默 fallback 到空 `AIProviderManager` → 真正 `run()`
时崩溃。

**修法**：

1. **升级到 0.8.12.15+**（**根治**）：

   ```bash
   pip install -U "krow-agent-sdk>=0.8.12.15"
   ```

2. 升级后仍报错 → 检查 `with_krow_api_key(...)` 是否真的传了 key（不能只 export `$KROW_API_KEY`
   而不传给 builder）：

   ```python
   agent = (
       AgentBuilder()
       .with_krow_api_key(os.environ["KROW_API_KEY"])  # ← 必须显式传
       .build()
   )
   ```

3. 异常本身（`LLMProviderUnavailableError`）会带"黄金错误模板"3 个修法建议——按提示走即可。

### Q2: `PermissionError: [Errno 13]` 写 `site-packages/`

**根因**：在 0.8.12.14 及以前，SDK 错把 `site-packages` 当 app root，非 root 用户运行时写
失败。

**修法**：

1. **升级到 0.8.12.15+**（**根治**）：

   ```bash
   pip install -U "krow-agent-sdk>=0.8.12.15"
   ```

2. 升级后显式设 `KROW_DATA_DIR` 到可写路径（强烈推荐 — 跨平台行为最确定）：

   ```bash
   ENV KROW_DATA_DIR=/home/krow/data
   ```

3. 不设 `KROW_DATA_DIR` 时，SDK 会按以下回退（按你的 OS）：

   - Linux: `$XDG_DATA_HOME/krow` → `~/.local/share/krow`
   - macOS: `~/Library/Application Support/Krow`
   - Windows: `%APPDATA%\Krow`

   SSOT：`modules/utils/portable_path.py:_get_writable_root`

### Q3: `docker build` 报 `/bin/sh: 1: ...: not found` / 容器 `/bin/sh` 损坏

**根因**：**不是** SDK 代码所致 —— 是 `python:slim` 多个 `RUN` 层之间 `dpkg-divert` 或
`/bin/sh → /bin/dash` 符号链接的瞬态状态问题。

**修法**：把所有 `apt-get install` + `pip install` 合并到**单一** `RUN` 层（如 §2.1 模板）。
不要拆成多个 `RUN`，也不要在两个 `RUN` 中间穿插 `apt-get` / `useradd` / `chown`。

### Q4: `pip install krow-agent-sdk` 报 "no matching wheel" / platform mismatch

**根因**：`krow-sdk-install` CLI 旧版（< 0.8.12.12）对 PEP 425 wheel tag 匹配过严。

**修法**：

```bash
pip install -U "krow-sdk-install>=0.8.12.12" "krow-agent-sdk>=0.8.12.15"
```

详 [`runtime-install.md` Q3.5](./runtime-install.md#q35-装时报--当前-host-没匹配的-runtime-wheel-pep-425-mismatch)。

### Q5: `agent.run()` 内 LLM 调用 timeout

**根因**：默认 HTTP timeout = 60s；如果走多 turn ReACT + 推理模型，可能不够。

**修法（当前）**：业务层加 retry 包装 + `try/except KrowSDKError` 自己重试。
**修法（roadmap）**：未来版本会暴露 `AgentBuilder.with_llm_timeout(...)` config；
关注 `roadmap.md` 更新。

### Q6: 中文字体显示成 □ 或乱码

**根因**：base 镜像缺 CJK 字体。

**修法**：`apt install fonts-noto-cjk`（§2.4 模板已含）。

### Q7: `OSError: cannot load library 'libpango-1.0.so.0'`

**根因**：你装了 `[visual]` 或 `[all]`，但 base 镜像缺 pango runtime（cairosvg 需要它做
text shaping）。

**修法**：按 §2.4 模板装：

```bash
apt install libpango-1.0-0 libpangocairo-1.0-0 libpangoft2-1.0-0
```

### Q8: K8s Pod 启动后 `CrashLoopBackOff`，日志只有 "Killed"

**根因**：很可能是 OOMKilled（agent 加载 ACT yaml + ToolManager + LLM provider 全套
初始化内存峰值约 400-600 MB；如果 `resources.limits.memory < 512Mi` 会被 OOM kill）。

**修法**：

```yaml
resources:
  requests:
    memory: "512Mi"
  limits:
    memory: "2Gi"   # 留出 agent.run 内 LLM context buffer
```

### Q9: 容器内 `KROW_API_KEY` 通过 K8s Secret 注入后仍报 401

**修法 checklist**：

1. `kubectl exec -it <pod> -- env | grep KROW_API_KEY` 确认 env 真的注入（拼写 / 大小写）
2. 确认 key 在 https://krow.cn/dashboard 没被撤销 / 没过期
3. 确认前缀 + 长度（`sk-user-` + 40 字符 = 48 字符整 / `sk-` 前缀任何 ≥ 20 字符 / `pk-pilot-` 联调用）
4. 任何 401 响应 header 里有 `X-Request-Id`，贴给 [support@krow.cn](mailto:support@krow.cn) 协查

---

## 7. 安全 / 合规 checklist（生产环境）

- [ ] `KROW_API_KEY` 通过 K8s Secret / HashiCorp Vault / AWS Secrets Manager 注入
      —— **绝不**写 Dockerfile / `ConfigMap` / git
- [ ] Pod `runAsNonRoot: true` + `runAsUser: 1000`（与 Dockerfile `useradd -u 1000` 对齐）
- [ ] `readOnlyRootFilesystem: true`，`KROW_DATA_DIR` 走 `emptyDir` / PVC mount
- [ ] `capabilities.drop: ["ALL"]` + `allowPrivilegeEscalation: false`
- [ ] PodSecurityAdmission `restricted` enforce
- [ ] NetworkPolicy 限制 egress（仅 `api.krow.cn` + 你显式 LLM provider endpoint）
- [ ] 镜像 trivy / snyk / grype 扫描通过
- [ ] log 不打印完整 API key —— SDK 日志已自动 redact，但你的应用层日志也要
- [ ] 容器 `terminationGracePeriodSeconds >= 300` 给 LLM 任务收尾

---

## 8. 进一步阅读

- [`quickstart.md`](./quickstart.md)：5 分钟上手 SDK + plugin 写法
- [`runtime-install.md`](./runtime-install.md)：拉私有 runtime wheel（`krow-agent-sdk-runtime`）
- [`api-reference.md`](./api-reference.md)：完整 `AgentBuilder` / `AgentV3Result` / 各类 Plugin Protocol API
- [`advanced-development-guide.md`](./advanced-development-guide.md)：进阶 plugin 设计哲学 + 测试范式
- [`roadmap.md`](./roadmap.md)：上线节奏 + 未来版本特性

---

## 9. 反馈

- 公开 Issues: [aullik5/krow-sdk-docs/issues](https://github.com/aullik5/krow-sdk-docs/issues)
- 公开讨论: [aullik5/krow-sdk-docs/discussions](https://github.com/aullik5/krow-sdk-docs/discussions)
- 私邮: [support@krow.cn](mailto:support@krow.cn)
- 商务: [sales@krow.cn](mailto:sales@krow.cn)

> 如发现本文档某个 Dockerfile 模板在你的环境里跑不通，请带上你的 base image / Python 版本 / Docker 版本 / 完整报错 `docker build` 输出提 issue —— Krow team 会复现并补充故障排查段。
