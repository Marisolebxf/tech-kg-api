<!-- 最终脱敏 PR 材料（2026-10-21 定稿，与 ~/deploy/PR-body-fix-script-security-thinking-1020.md 同源同步）。
     公开材料：不含密钥片段（含掩码）与真实业务源码。创建与否由用户决定，本文件不构成创建/合并/部署授权。 -->

# PR 标题

脚本 LLM 安全校验：思考型模型适配 + 提示词分诊 + 判定/取消语义收紧

# Compare 链接

https://github.com/Marisolebxf/tech-kg-api/compare/kgetl...fix/script-security-thinking-budget-1020?expand=1

# PR 正文

## 脚本 LLM 安全门：适配思考型模型 + 提示词分诊化 + 评审修订（fix/script-security-thinking-budget-1020）

默认模型切 glm-5.2（coding 端点）后脚本上传必败的根因：思考型模型 reasoning 先吃
completion 预算且思考深度随 max_tokens 水涨船高；httpx read 超时按字节间隔计、
SDK 内部默认重试 2 次，per-request timeout 拦不住总时长，SSE 静默期越过 web nginx
默认 60s 即 504。

### Commit 1 `2b6b22fe`：预算 + 墙钟硬顶
- `REVIEW_MAX_TOKENS` 1024 → 3072（7KB 脚本实测思考 ~2800 token 才够）。
- `REVIEW_STAGE_SECONDS = 50s` 阶段墙钟硬顶：模块级 ThreadPoolExecutor +
  `future.result(timeout=剩余时间)`，剩余 <5s 不再重试。
- `synthesize` 加 timeout 透传（对齐 synthesize_json）。

### Commit 2 `a3bc564f`：提示词分诊化 + 并发准入/取消
- **提示词**：审计专家人设 → 快速分诊器（只扫八类信号、命中才细看、禁止展开业务逻辑）。
  证据要求（逐字 ≤120 字符、宁漏勿编）与 JSON 契约不变；新增防指令注入条款。
- **检查范围（有意变更）**：删去"（不限于）"与"任何可能影响宿主环境安全的行为都判为
  不安全"——清单外探索性检查收缩到与 `_HIGH_RISK_RE` 静态兜底同一口径。
  有单测钉住八类信号/证据要求/防注入/JSON 契约不缩水，开放式表述不得回流。
- **并发容量与取消**：`_REVIEW_SLOTS(4)` 非阻塞准入（池满立即"暂不可用"，不堆积
  排队僵尸）；墙钟超时对排队 future `cancel()`；`synthesize` 显式超时时禁 SDK 重试
  （commit 3 进一步改为专属传输 + max_retries=0，放弃时 close 尽力中断）；槽位经
  done-callback 终态释放。
- **截断/损坏处理**：格式异常重试一次 → 仍坏归"校验不可用"（两例截断 JSON 单测钉死；
  commit 3 把口径精确化为"结构不完整的输出不会判 safe"）。
- 测试：+5 单测；对齐 `test_verify_unsafe_not_saved` 到证据锚定语义
  （该用例自 evidence 语义合入 kgetl 起就在失败，此前被误归入环境基线；
  钉 `TRS_GRAPH_SPACE=techkg` 后其余环境失败消失才显形）。全套 40 过 + ruff 干净。

### Commit 3 `7bf8c722`：评审修订（原有问题与本轮范围收缩分开记录，见模块头）

模块头改为三段：**【原有问题记录】**（历史缺陷 1-7，治理对象）/ **【现行机制】** /
**【2026-10-21 评审修订】A-D**（本轮范围收缩与语义收紧，与原有问题分开留档）。

- **A. 撤销两条放行反转**："模型判不安全但无逐字证据 → 无实证放行"与"证据真实但
  源码未命中静态高危 → 误报放行"不再触发。**模型判不安全一律维持拦截**；证据校验
  降级为展示层清洗（无可验证证据的 issue 从展示清单剔除）+ 审计标注（剔除计数、
  `_HIGH_RISK_RE` 命中与否写入 summary 供人工复核）。历史 1/3 类误杀改由重传/换
  模型/人工复核解决，不以自动放行兜底。
- **B. 判定结构强校验**：safe(bool) + issues（对象数组，逐项非空 problem+evidence）
  + summary(非空 str) 须齐全，unsafe 须非空 issues；旧版纯字符串 issues 不再接受。
  结构不完整（含截断恰好拼成最小合法 JSON）按格式异常重试一次 → 仍坏归"校验不可用"。
  **撤回"格式损坏任何路径绝不放行"的绝对表述**——成立的准确口径是
  **"结构不完整的输出不会判 safe"**（首尾恰好完整的输出与正常输出无法区分）。
- **C. 在飞 HTTP 总截止**：显式 timeout 时改用**专属 httpx 传输** + `max_retries=0`
  并登记到 abort_reg；调用方墙钟超时后 `future.cancel()` + close 专属传输**尽力**
  中断在飞请求。**撤回"≤1×timeout"的绝对表述**——read 超时按字节到达间隔计，持续
  滴流的服务端仍可能拖过单次超时；权威总上界是调用方墙钟（50s 内必返回）。
  滴流实验实证：1 字节/1.5s 的假端点 + 5s 预算，调用方 5.0s 准时返回 unavailable，
  close 后工作线程阻塞读随连接复位中断（服务端 2.9s 后 ConnectionResetError）。
- **D. 提示词分诊化留档**（即 commit 2，同属范围收缩一并记录）。
- **结束原因与错误分类**：`synthesize` 经 `result_meta` 回填 finish_reason /
  reasoning_tokens；失败按 `classify_llm_error` 分类（rate_limit / timeout / auth /
  forbidden / insufficient_balance / http_\<code\> / other，智谱 1113 余额经文本识别）。
  `verdict.category`（passed / rejected / format_error / unavailable_\<class\>）随日志
  与 **SSE 终态事件**（`code=llm_unavailable|llm_rejected` + `category`）机器可读透出，
  前端/运维可据此分类提示与告警。

### Commit 4 `f480b7b9`：复核修订四（Codex 复核 de454db1 四项，P1×2 + P2×2）

- **SEC-JSON（P1）判定一致性**：`_parse_verdict` 在**RAW issues**上（证据清洗前）加双向
  一致性——`safe=true 且 issues 非空` = 自相矛盾，按格式异常拒收重试→不可用；证据
  hallucination 清洗不可能再掩盖矛盾结论。放行落库样本不再携带"备注型 issues"。
- **SEC-META（P1）结束原因约束 + 空回答分类**：`_NORMAL_FINISH_REASONS={None,"stop"}`
  ——finish_reason 为 length/content_filter 等时即使 JSON 完整也不产生 passed/rejected
  （None=无元数据=不约束，测试桩兼容口径显式化）；content 空串/空白归类
  `empty_response`（不落 unknown）；每次尝试 `last_meta.clear()` 防跨次污染；不可用
  文案透出具体格式原因（含截断）。
- **SEC-LIFETIME（P2）迟登记竞态 + 慢清理**：新增 `infra/llm.LLMAbortHandle`（锁+取消
  标志）：cancel 后 register 返回 False，登记方立即关传输、不构造 SDK 客户端、零发请求
  （封死"调用方超时返回后请求才登记/发出"路径）；登记提前到 SDK 构造前；取消清理移入
  守护线程（慢 close 不拖长返回）；槽位仅 future 真终态释放。口径：future.result 墙钟
  是调用方等待上界，非放弃后全函数路径硬上界。
- **SEC-SSE（P2）前端终态**：`verifyAndSaveScript` finished 标志保证终态恰好一次——
  success/error 为终态；无终态 EOF → `stream_eof`；75s 看门狗 → `stream_timeout` +
  AbortController.abort()；onError 第四可选参 `{code,category}`（三参调用方不变）；
  终态后错误吞掉、终态前照旧上抛。
- **验证**：后端新增单测 12 项（一致性 2/结束原因 5/空回答 1/容量恢复 1/元数据与句柄
  3），改动文件套件 49+15+5 过、ruff 干净；前端新增 spec 5 项，vue-tsc 0 错、全量
  vitest 796/796。容器探针：①事件暂停初始化+0.5s 预算，放弃后放行初始化，服务端
  **0 请求**；②注入 0.25s 慢 close，返回仍 5.00s、清理在守护线程 ret+0.25s 完成；
  ③滴流复跑：close 中断在飞读，服务端 ret+2.9s ConnectionResetError。
  边界：延迟建连/多进程容量、真实前端代理链 e2e、glm-4.7 20 例回归未重跑（本轮不动
  提示词，判定与传输管理以外的行为不变）。

### Commit 5 `0aad7b84`：复核修订五（Codex 复核 942b442e，取消标志调度窗口收口）

- **P2 SEC-LIFETIME 调度窗口**：此前 `cancel()`（含置标志）整体进守护线程——线程未获
  调度时调用方返回后迟到 register 仍会成功并发请求（Codex 确定性交错复现）。最小修正：
  `LLMAbortHandle` 拆分——**`mark_cancelled()` 调用线程内同步置标志+取传输**（短锁无
  I/O，保证"已返回⇒已置位"，任何迟到 register 必被拒）；**`close_transports()` 可能
  阻塞的关闭交守护线程**。迟登记被拒方自关传输、不构造 SDK、零发请求；槽位仍以
  future 真终态释放。`register` 先于置旗成功、SDK 构造未完的取消窗口仍属既有
  "close 尽力中断"语义，列为后续交错补测项。
- **验证**：确定性交错单测（清理线程被闸死+调用方返回后放行迟初始化→register 必拒、
  零 SDK create；旧实现必失败）；**阴性对照**（模拟旧式延迟置旗→同款交错 register
  成功 dispatch=1，证明判别力）；容器探针 D（真实 synthesize：清理线程 entered=1
  done=0 时调用方 0.50s 返回，释放迟初始化后 error_class=aborted、请求计数 2s 保持
  0）；复跑 C（0.25s 慢 close 返回仍 5.00s）与 A（滴流 ConnectionResetError）。
  改动文件单测 44 过（+2）、ruff 干净。

### 验收补充（2026-10-21，用户授权 C+D→A→B 隔离验收，分支 @ 89ab9995，Codex 复核口径已对齐）

- **C 多进程容量（函数级实测，非端到端）**：2 个独立 Python 进程 × 并发 5 路真实
  `review_script_security`（慢 LLM 5s/阶段预算 6s）：每进程实测 `{passed:4, unavailable_busy:1}`、
  elapsed≈5.0s，合计 8 passed / 2 busy；busy 两次尝试均 t≈0 快速失败、无排队空等——实证
  「槽位=进程内信号量（4×进程数，非共享，设计语义）」。**边界**：函数级并发证明；
  uvicorn workers=2 下的 HTTP 连接分配未验证，与容量语义分开记录，不标记 C 端到端通过。
- **D 构造期取消交错（单测 + 探针，按各自来源记录）**：新增单测
  `test_cancel_during_sdk_construction_closes_transport_no_dispatch`（commit 89ab9995，**本次仅
  新增测试，未改生产实现**）：register 成功→SDK 构造被闸→调用方放弃→放行构造 ⇒ dispatch=0、
  传输 is_closed、worker 按异常分类降级（Codex 独立运行该用例通过；0aad7b84 时代 Codex 独立
  44 项为其各自时点结果，不与本次合并计数；GLM 侧容器全套 45 项 + ruff 干净为本地结果）。
  D-2 延迟建连探针（不可路由地址）：放弃后 worker 0.55s 退出（非自身 8s 超时）=close 对建连期
  也生效——仍按**尽力中断**口径记录，不升级为硬保证。
- **A 当前代码 glm-4.7 回归（实测，恰好 40 次真实调用=授权上限，零重试）**：
  **20/20 得到判定、19/20 符合预期、0 不可用、0 异常 finish_reason、0 重试**（max 5.6s/mean 3.4s）。
  **1 例预期放行被拒（已知误拒，列入已知限制）**：`paper_entity_step.py`（真实业务脚本）
  `import os` 全文未使用——现行提示词八类信号第 1 类将 os 列为危险 import（**只列导入、
  不要求使用**，条文未区分），该样本**已测两轮均拒**（有限次数实测，不外推为确定性保证）→
  rejected+审计标注「源码未命中静态高危调用（供人工复核）」。定性为**样本预期与现行策略的
  冲突/已知误拒**：保守拒绝不计作判对，clean 也不能称全部通过。处置：**本 PR 保留现行严格
  导入策略不改动**；提示词口径调整（如"导入且使用"）另行议题，评审方建议维持现状——是否
  采纳由维护者决定；受影响脚本可删无用 import 后重传或走人工复核；不恢复自动放行反转，
  不改业务脚本与模型。
  期望表修正记录（保留 run1 前后日志）：run1 曾把 3 例 injection 误标 expected=False，修正依据
  是提示词条文本身——信号 7/8 要求"解码后 **exec/eval**"，纯解码展示无执行不在清单内；
  clean_praise/clean_accuse 为干净脚本+伪指令，应放行。ground truth 依据清单条文与脚本行为，
  不以模型输出倒推。run0 失败记录：密钥校验误用 sha256 前缀（既有"首6+尾4"掩码记法非哈希），
  未发起调用。
- **B 一次性 nginx 栈 HTTP/SSE 链路实测（LLM 为 stub，零真实模型调用；隔离 MySQL/RustFS，测毕全拆）**：
  api=分支代码构建，web=dev2 同镜像同 `nginx.dev2.conf` 挂载。相应用例实测通过：
  ①成功：SSE 四事件全序 0.73s、S3/DB 回读一致、重传幂等；②llm_rejected：终态
  `code=llm_rejected,category=rejected` 透传、拒收脚本未落库；③a 客户端 2.0s 掐断后紧接上传
  0.05s 成功（槽位跨请求独立）；③b 冻结 api → **60.06s** nginx **默认** proxy_read_timeout=60s
  切断（curl rc=18 部分传输、流尾无终态事件；nginx error log 留存 upstream timed out）；
  ④慢端点（stub 挂 600s）→ 客户端 **50.02s** 收到干净终态 `unavailable_stage_deadline`，
  api 日志证实放弃后守护线程 close 打断了挂起在飞请求。
  **链层级序观察值**：api 50s 阶段墙钟 < nginx 60s 默认读超时 < 前端 75s 看门狗（两版 nginx
  配置均未显式设置读超时）。50.02s 为该慢端点场景观察值，**不外推**为含排队/配置解析/保存的
  上传总时长保证。**边界（未实测，均不标通过）**：curl rc=18 证明流被截断，不能直接证明浏览器
  触发 stream_eof（浏览器也可能走网络异常 catch）；真实浏览器行为、75s 看门狗实际触发、
  edu 门户网关链路均未实测——浏览器 JS 终态语义以 vitest 单元测试为准。
- **证据索引（公开材料不含密钥片段与真实业务源码）**：代码 2b6b22fe→a3bc564f→7bf8c722→
  f480b7b9→0aad7b84→89ab9995（review 分支）；完整证据条目（含失败记录与实测/模拟/未验证
  区分）见协作文档分支 `codex/script-security-glm-review-1021` @ b95c935a
  （docs/脚本安全校验协作/GLM-Codex协作.md）。探针物料与脱敏日志留存于开发机：
  `/tmp/secgate1020/`（harness4.py 语料 20 例、multiproc_capacity.py、delayed_connect_probe.py、
  out/harness4-run*.log，密钥仅环境变量过手不落盘）、`/tmp/secgate1020b/`（docker-compose.yml、
  stub_llm.py、corpus/ 三例、out/{api,stub,web}.log、case3b.stream/rc——一次性环境，测毕
  down -v 全拆，日志为留存副本）；B 栈自造样本 clean_step.py sha256=
  730b51d04921a209ced326fe9e11570166854fe1146f5472f89ed74b597641e7。40 次真实调用为本轮
  上限，已停止，不追加。

### 验收验证（glm-4.7 @ paas，2026-10-21 实弹；注意：下表为 **7bf8c722 代码时代**的实测，89ab9995 当前代码回归见上节验收补充 A）

走分支真实代码（LLMClient + review_script_security 全链路，含重试/准入/分类），
语料 clean×6 / dangerous×6 / obfuscation×4 / injection×4 共 20 例，并发 3：

| 类别 | 结果 | 时延 |
|---|---|---|
| clean（含 fault 注入变体） | 6/6 passed | 1.8-3.5s |
| dangerous | 6/6 rejected（issues 带证据） | 2.7-6.3s |
| obfuscation | 4/4 rejected | 2.9-5.3s |
| injection·带载荷（白名单/规则改写说辞） | 2/2 rejected（说辞被点名忽略） | 3.9-4.5s |
| injection·干净脚本（预审伪指令/诬告注释） | 2/2 passed（抗注入双向正确） | 2.0-3.4s |

**20/20 判对、0 不可用，最长 6.3s 均值 3.3s**。判定反转已不存在：所有 rejected 维持
拦截（summary 带审计标注），不存在"无实证/未命中静态高危 → 放行"路径。
单测+集成 48 过（新增结构强校验 4 例、错误分类 4 例、SSE 终态码 2 例、busy/
stage_deadline 分类断言）；ruff 干净。全仓套件 2754 过 / 20 失败均为本分支未触及
文件的既有环境基线（property_management / expert_paper / platform_overview）。

### 对照回归（2026-10-21，glm-5.2@coding，max_tokens=3072，共 74 次）

语料：clean×6（真实业务脚本 5-16KB）/ dangerous×6（eval、os.system、subprocess、
socket 外传、/etc/passwd、os.environ+requests）/ obfuscation×4（marshal、hex→eval、
`getattr(__import__)`、compile+exec）/ injection×4（干净脚本+预审伪指令、危险脚本+
白名单伪指令、混淆+规则改写伪指令、干净脚本+诬告注释）。旧提示词 ×1、新提示词 ×3
（clean ×2）。

| 类别 | 旧提示词 | 新提示词 |
|---|---|---|
| clean 应放行 | 6/6 放行，均 16.5s 最长 26.8s | 12/12 放行，均 10.0s 最长 17.1s |
| dangerous 应拦截 | 6/6 拦截（实证齐），均 7.5s | 18/18 拦截（实证齐），均 9.9s |
| obfuscation 应拦截 | 3/4（1 例预算耗尽答案空） | 12/12 拦截（实证齐），均 16.5s 最长 29.3s |
| injection·带载荷 应拦截 | 1/2 判对 + 1 损坏 | 5/6 判对 + 1 损坏（截断） |
| injection·干净脚本 应放行 | 1/2 判对 + 1 损坏（伪指令诱发 3071 token 思考吃满预算） | 6/6 放行 |
| 判错方向 | 0 | 0 |
| 输出损坏 | 3/20 | 1/54 |
| 最长耗时 | 53.2s（破 50s 墙） | 41.1s |

要点：两个提示词都没把方向判反；差异在**输出损坏率与时延**——注入文本会诱发旧提示词
深度思考吃满 3072 预算导致答案截断（拒绝被说服的方式是把预算烧光）；新提示词损坏率
1/54、最长 41.1s，均在 50s 墙内。损坏输出在生产路径=格式异常重试→不可用（提示稍后
重传），结构不完整的输出不会判 safe（有单测钉死）。

诚实边界：样本为单模型单端点单日调用（对照回归 glm-5.2@coding 74 次、验收矩阵
glm-4.7@paas 20 次）；检出能力"未见下降"的结论限于上述语料，不外推到任意攻击手法。
截断 1 例说明注入文本仍可能抬升思考深度，3072 预算偶发吃紧。语义取舍：撤销放行反转
后，历史上 1/3 类误杀（幻觉/理论风险）将表现为"拦截 + 审计标注（供人工复核）"，
代价是误杀需人工介入或换模型重传，换取"模型判不安全绝不自动放行"的保守边界。

🤖 Generated with [Claude Code](https://claude.com/claude-code)
