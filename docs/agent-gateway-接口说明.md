# agent-gateway 接口说明文档

> 供外部 agent 通过 HTTP 操作本机（dev2 开发机 10-50-183-56）的命令执行网关。
> 版本：v1（2026-10-30 部署）　维护人：zhangzhong_e43d4db3

---

## 1. 概述

| 项 | 说明 |
|---|---|
| 形态 | HTTP REST（纯 Python 标准库实现，零依赖） |
| 地址 | `http://10.50.183.56:9787`（内网可达；本机回环 127.0.0.1 同端口） |
| 认证 | `Authorization: Bearer <token>`（48 字节随机 token，向管理员索取） |
| 能力 | 执行任意 shell 命令（以本机用户 `zhangzhong_e43d4db3` 身份，`bash -c`） |
| 审计 | 全部请求（含认证失败）落盘 `~/agent-gateway/audit.log` |
| 部署 | nohup 后台进程，`~/agent-gateway/start.sh` / `stop.sh` 启停 |

**安全级别：持 token = 可在本机执行任意命令。** token 仅发给信任的 agent/使用者，不得写入代码仓库或群聊。

---

## 2. 快速开始

### curl

```bash
TOKEN=<向管理员索取>
curl -s -X POST http://10.50.183.56:9787/exec \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"command":"hostname && docker ps --format \"{{.Names}}\"","timeout":30}'
```

### Python

```python
import json, urllib.request

def exec_remote(command: str, timeout: int = 120):
    req = urllib.request.Request(
        "http://10.50.183.56:9787/exec",
        data=json.dumps({"command": command, "timeout": timeout}).encode(),
        headers={"Authorization": "Bearer <token>", "Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=timeout + 30).read())

print(exec_remote("df -h / | tail -1"))
```

### 探活（免认证）

```bash
curl -s http://10.50.183.56:9787/health
# {"ok": true, "service": "agent-gateway", "time": 1793334667}
```

---

## 3. 接口明细

### GET /health —— 探活（免认证）

响应：`{"ok": true, "service": "agent-gateway", "time": <unix秒>}`

### GET / —— 服务自描述（免认证）

返回端点清单，无敏感信息。

### POST /exec —— 执行命令（需 token）

**请求体**（JSON）：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `command` | string | ✅ | 要执行的命令，经 `bash -c` 运行；非空 |
| `timeout` | number | ❌ | 秒，默认 120，上限 **600**；超时进程被杀 |
| `cwd` | string | ❌ | 工作目录，必须是**已存在**的目录，否则 400 |
| `env` | object | ❌ | 额外环境变量，string→string，叠加到继承环境 |

**响应**（200）：

| 字段 | 说明 |
|---|---|
| `exit_code` | 命令退出码；**超时被杀为 null** |
| `stdout` / `stderr` | 标准输出/错误（UTF-8，容错解码） |
| `truncated` | 任一流超 5MB 被截断时 true |
| `timed_out` | 超时终止 true |
| `duration_ms` | 耗时毫秒 |

**错误码**：

| 码 | 场景 |
|---|---|
| 401 | 缺失/错误 token（记审计 `auth_failed`） |
| 400 | body 非 JSON、`command` 空、`timeout` 越界、`cwd` 不存在、`env` 类型错、body >1MB |
| 404 | 路径不存在（只有 `/`、`/health`、`/exec`） |
| 500 | 命令启动失败（如 fork 失败） |

---

## 4. 保护限值一览

- 单命令超时 ≤ 600s（默认 120s），到点 kill
- stdout / stderr 各 ≤ 5MB，超出截断并置 `truncated: true`
- 请求体 ≤ 1MB
- 多线程并发：支持（ThreadingHTTPServer，每请求一线程）

**长任务建议**：超过 10 分钟的活不要直接 `/exec` 同步等，先放后台再轮询：

```bash
# 第 1 步：放后台、落盘
/exec {"command":"nohup bash myjob.sh > /tmp/myjob.log 2>&1 & echo started"}
# 第 2 步：轮询
/exec {"command":"tail -5 /tmp/myjob.log; pgrep -f myjob.sh || echo FINISHED"}
```

---

## 5. 审计与日志

- **审计** `~/agent-gateway/audit.log`（JSONL，每行一事件）：

```json
{"ts":"2026-10-30 12:31:07","ip":"10.50.1.22","event":"exec","command":"docker ps","cwd":null,"timeout":120,"exit_code":0,"timed_out":false,"duration_ms":119}
{"ts":"2026-10-30 12:31:07","ip":"10.50.1.22","event":"auth_failed"}
```

- **服务日志** `~/agent-gateway/server.log`（启动/异常栈）

查谁在操作：`tail -f ~/agent-gateway/audit.log`；`event` 取值：`server_start` / `server_stop` / `exec` / `auth_failed`。

---

## 6. 运维

```bash
~/agent-gateway/start.sh          # 启动（已在运行则跳过，幂等）
~/agent-gateway/stop.sh           # 停止
```

- **轮换 token**：直接覆盖 `~/agent-gateway/token` 内容（每次请求实时读取，无需重启）。
- **重启后恢复**：当前为 nohup 部署，机器重启后需手动执行一次 `start.sh`（如需开机自启再补 systemd/cron）。
- **怀疑泄漏**：`stop.sh` 立即下线 → 覆盖 token → 对照 `audit.log` 排查异常 IP。

---

## 7. 本机环境速查（给接入 agent 的上下文提示）

| 资源 | 访问方式（均可经 /exec 执行） |
|---|---|
| Docker 栈 | `docker ps`；主要容器：`tech-kg-api-dev2`(8002)、`tech-kg-web-dev2`(8089)、`tech-kg-temporal-worker-dev2` 等 |
| MySQL | `tech-kg-mysql:30306`（库：techkg_platform_dev2 / gkx_kg_v2 / gkx_dwd_local / gkx_element…）；容器内走 `host.docker.internal` |
| 图库 REST | `http://host.docker.internal:8090`（trs-graph，头 `X-API-Key` + `X-Graph-Space`） |
| api 容器内执行 Python | `docker exec -i tech-kg-api-dev2 .venv/bin/python - << 'EOF' ... EOF`（**必须带 -i**） |
| 部署目录 | `~/src/tech-kg-api-dev2`（dev2 主栈，5 文件 compose） |

> 提示：容器内没有 curl，用 `.venv/bin/python` + urllib。

---

## 8. FAQ

**Q: 返回中文乱码？**
输出按 UTF-8 容错解码，一般不乱；若命令本身输出 GBK（如某些老工具），在命令里转一下：`... | iconv -f GBK -t UTF-8`。

**Q: 命令带引号怎么写？**
JSON 里整体转义即可；复杂命令建议 `base64`：`echo <b64> | base64 -d | bash`。

**Q: 并发会互相影响吗？**
每请求独立 bash 进程，互不影响；但同时操作同一资源（如 docker compose 重建）需自行避让。

**Q: token 放哪？**
向管理员索取 `~/agent-gateway/token` 内容；不要提交进仓库/聊天记录。
