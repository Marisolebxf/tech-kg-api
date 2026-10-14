# gkx 生产库抽取——前端部署手册（2026-10-13）

> 目标读者：在一个**空白环境**里、只用平台前端（本环境入口 8093）把 gkx 生产格式样例库
> （`183.240.141.251:3318/gkx`，只读账号）的全量抽取搭起来并跑完的操作者。
> 工程依据与设计取舍见 `docs/gkx生产库抽取适配绑定清单.md`（下称《绑定清单》）；本手册只讲
> **怎么操作、每步核对什么、遇到什么算正常**。
>
> 硬约束（沿用）：外部库**不能动表结构、不能改表数据**——全部适配靠 querySql + 脚本转换层。
> 数据源密码只在注册表单里填一次，**不写入任何文档/物料**。
>
> **验证状态（2026-10-13）**：本套物料已在 `gkx_verify_1` 空间完成三链 e2e 验证
> （实体链 16 环全量 + 关系链A 14 环 / 关系链B 13 环按每绑定首 1 万行封顶），
> 45 脚本全通过、锚点对账全中（Product 47,956 / IndustryNode 1,261 / News·产业链
> 108,052 / CHILD_OF 1,261 精确）。全量部署按本手册照跑即可；对账明细与缺陷全录
> 见《绑定清单》§8。

## 0. 全景：要搭的东西

| 物料 | 数量 | 说明 |
| --- | --- | --- |
| MySQL 数据源 | 1 | `gkx-prod-sample` |
| 实体 Schema | 16 | TAG 落目标图空间 |
| 关系 Schema | 33 | EDGE；其中 2 个（实际控制/受益所有人）外部无源、**有意零绑定** |
| 抽取脚本 | 45 | 文件在 `backend/script/yunfei_restore/`（另 3 个是 mixin/fallback 辅助件与 2 个无源关系，不上传） |
| 数据来源绑定 | 151 条 / 47 Schema | 每条 = 旧表名标签 + 主键列 +（可选）querySql |
| 手工名字列索引 | 7 个 TAG INDEX | 平台只自动建 `name` 单列索引，缺这 7 个跑 Person/Organization 环会把共享图库打爆（缺陷㉝） |
| 链任务 | 3 条 | 实体链 16 环 → 关系链A 14 环 → 关系链B 13 环，**严格串行** |

预计耗时：实体链以天计（~2000 万行源库、写入受限流保护，见 §7 慢因），期间需要若干次
「重触发续跑」（设计内，见 §5）。

## 1. 物料准备（推荐：从现网导出）

最可靠的物料来源是**已经验证过的现网环境**（如 gkx_verify_1）。用平台 API 一键导出三件套
（49 Schema 定义、45 脚本、151 绑定），在 api 容器内执行：

```bash
docker exec -w /app -e PYTHONPATH=/app <api容器> .venv/bin/python - <<'EOF'
import httpx, json
base = "http://localhost:8000/api/v1"
c = httpx.Client(timeout=60)
out = {"schemas": [], "bindings": {}, "scripts": {}}
r = c.get(f"{base}/schema-management/schemas", params={"graphSpace": "gkx_verify_1", "pageSize": 100})
body = r.json(); items = body.get("data") if isinstance(body, dict) else body
if isinstance(items, dict): items = items.get("items") or []
for s in items:
    d = (c.get(f"{base}/schema-management/schemas/{s['id']}").json().get("data") or {})
    out["schemas"].append(d)
    out["bindings"][s["name"]] = d.get("sources") or []
    sc = d.get("script")
    if sc: out["scripts"][s["name"]] = sc          # 脚本内容在 script 字段
json.dump(out, open("/tmp/gkx-deploy-material.json", "w"), ensure_ascii=False, indent=1)
print("exported", len(out["schemas"]), "schemas /", sum(len(v) for v in out["bindings"].values()), "bindings")
EOF
docker cp <api容器>:/tmp/gkx-deploy-material.json .
```

导出文件随身带走（注意：**不含密码**）。脚本也可以直接用仓库里的生成物
`backend/script/yunfei_restore/*.py`（`git checkout 7a1fbba0 -- script/yunfei_restore/ &&
uv run python script/tools/build_portable_steps.py` 重新生成，49/49 校验通过）。
文件与 Schema 的对应关系以导出物料里的 `scripts` 字段为准（15 实体 + 30 关系；
`organization_base_mixin.py`、`authored_by_fallback_relation_step.py` 是辅助件不上传；
`actual_controller_of_*`、`beneficial_owner_of_*` 两脚本对应无源关系，不必上传）。

> 兜底：`artifacts/gkx-prod-bindings/manifest.json` 有全部 querySql，但它是 10-10 版本，
> 不含 10-11 干跑后的手工修订（列精简/删 4 条专利冗余绑定）——**以现网导出为准**。

## 2. 前端操作步骤

### ① 图空间

图谱构建页全局图空间选择器 → 新建图空间（如 `gkx_prod`）→ 选中。后续所有 Schema/任务都
落在这个空间。新建后 Nebula 有秒级~十秒级传播延迟，属正常。

### ② 注册 MySQL 数据源

管理端「配置管理 → MySQL 数据源」→ 新建：

| 字段 | 值 |
| --- | --- |
| 名称 | `gkx-prod-sample` |
| 主机 | `183.240.141.251` |
| 端口 | `3318` |
| 默认库 | `gkx` |
| 用户名 | `gkx_reader_zp` |
| 密码 | 部署时经环境/表单提供（只读账号，不落文档） |

### ③ 建 16 个实体 Schema

「Schema 管理 → 实体」逐个新建，属性集逐条照物料抄（name/dataType/required/identityKey/
graphSpace=目标空间）。建完后**逐个点开核对 DDL 状态 = 成功**——创建接口 200 ≠ DDL 成功，
新建空间有「TAG 静默建丢」窗口（缺陷㉔；若失败用平台「执行 DDL」重跑即可补建）。

16 个实体（链上顺序）：科技成果 Report / 项目 Project / 产品 Product / 科技专家 Person /
专利同族 PatentFamily / 专利 Patent / 论文 Paper / 机构基础信息 OrganizationBase / 机构
Organization / 新闻资讯 News / 技术主题 Keyword / 期刊 Journal / 产业链节点 IndustryNode /
产业链 IndustryChain / 事件 Event / 数据来源 DataSource。

### ④ 建 33 个关系 Schema

「Schema 管理 → 关系」，端点在表单下拉里选已建好的实体（源/目标 + 表达式），属性照物料。
其中 **ACTUAL_CONTROLLER_OF、BENEFICIAL_OWNER_OF 建完不绑任何来源**（外部库无源表，
「无源即 0」口径，属设计内）。

### ⑤ 上传 45 个脚本

每个 Schema 详情 → 转换步 → 上传对应 `*_step.py`。保存时平台做语法+入口校验，**并走 LLM
审核通道**（缺陷⑰：审核结论不可复现）。最稳姿势：部署环境**不配 LLM key**（审核自动降级，
只做代码级校验）；若必须配 LLM，遇到拦截重试即可，45 个脚本语义均为纯转换、无危险调用。

### ⑥ 灌 151 条绑定

每个 Schema 详情 → 数据来源 → 逐条新增（物料 `bindings` 字段）：

- **表名**填物料里的旧表名（它是显示标签+默认读取对象）；
- **querySql** 非空的绑定：把 querySql 原文粘贴进 querySql 输入框——**实际读取走 querySql**
  （keyset 分页、列别名、治理过滤都在里面）；
- **主键列**照物料（querySql 绑定留空时间列 = keyset 模式）；普通表绑定的平台 OFFSET 语义
  与旧版一致；
- 同一 Schema 多条绑定（如 Patent 的 A 裸表 + B 富集双源）是设计内的并发抽取，属性集
  不相交、列级 upsert 不互踩；
- ⚠ 缺陷⑭：某些编辑路径会抹掉已填的 querySql——**每灌完一个 Schema 就点开复查一遍
  querySql 还在**，再进下一个。

各 Schema 绑定数（实况口径，共 151）：

| Schema | 绑定 | Schema | 绑定 | Schema | 绑定 |
| --- | --- | --- | --- | --- | --- |
| Person | 16 | Event | 15 | OrganizationBase | 14 |
| Organization | 10 | Product | 10 | INVOLVED_IN | 16 |
| Keyword | 6 | CITES | 6 | Report/Patent/Project/Paper/News/Journal | 各 2 |
| AUTHORED_BY / SHAREHOLDER_OF / EXECUTIVE_OF / PRODUCES / PUBLISHED_IN / FUNDED_BY / HAS_OUTPUT / HAS_PARTICIPANT / LEADS / OUTPUT_OF | 各 2 | 其余 25 个 | 各 1 | ACTUAL_CONTROLLER_OF / BENEFICIAL_OWNER_OF | 0 |

### ⑦ 手工补 7 个名字列索引（必做，否则跑挂）

平台只自动建 `name` 单列索引；同名消歧召回会对**全部名字列**发 OR 查询，多列 OR 使 name
索引失效 → 全 tag 扫 → 共享 storaged CPU 打爆（缺陷㉝ 实锤「死亡循环」）。图库控制台/
`POST /api/v1/query`（X-Graph-Space: 目标空间）逐条执行：

```ngql
CREATE TAG INDEX idx_person_name_cn ON Person(name_cn(64));
CREATE TAG INDEX idx_person_name_en ON Person(name_en(64));
CREATE TAG INDEX idx_person_name_zh ON Person(name_zh(64));
CREATE TAG INDEX idx_organization_name_cn ON Organization(name_cn(64));
CREATE TAG INDEX idx_organization_name_en ON Organization(name_en(64));
CREATE TAG INDEX idx_journal_name_zh ON Journal(name_zh(64));
CREATE TAG INDEX idx_journal_name_en ON Journal(name_en(64));
-- 逐个 REBUILD（异步任务，SHOW TAG INDEX STATUS 看到 FINISHED 即可）：
REBUILD TAG INDEX idx_person_name_cn;
-- …其余 6 个同款
```

实测效果：OR 召回 0.85s → 0.018s（47×），零代码改动、语义不变。

### ⑧ 建 3 条链任务

「图谱构建 → 新建任务」→ 任务类型选**链**（多 Schema 严格串行），batchSize **2000**
（默认 500 对两千万行库会产生 4 万批；payload S3 中转开着，2000/批在 8MB 预算内安全），
数据源选 `gkx-prod-sample`，图空间选目标空间。三链构成（环序照抄，顺序即执行序）：

| 任务名 | 环数 | 环序 |
| --- | --- | --- |
| gkx验证-实体链 | 16 | 科技成果 → 项目 → 产品 → 科技专家 → 专利同族 → 专利 → 论文 → 机构基础信息 → 机构 → 新闻资讯 → 技术主题 → 期刊 → 产业链节点 → 产业链 → 事件 → 数据来源 |
| gkx验证-关系链A | 14 | 子公司关系 → 就读所属院校 → 涉及风险事件关系 → 论文引用关系 → 股东持股关系 → 产业资讯报道产业链 → 专家合著关系 → 家族成员关系 → 被参考 → 企业生产产品 → 论文发表关系 → 产业上下游 → 成果产出关系 → 投资关系 |
| gkx验证-关系链B | 13 | 产业节点上下级 → 论文主题 → 企业关联资讯 → 项目资助方 → 项目参加人 → 产业链包含产业节点 → 法定代表关系 → 项目负责人 → 高管任职关系 → 任职关系 → 企业归属产业链节点 → 收购 → 论文署名关系 |

### ⑨ 触发：严格串行

**实体链先跑完，再触发关系链A，再关系链B**。原因：FUNDED_BY/LEADS/HAS_PARTICIPANT/
HAS_OUTPUT 是图匹配器关系（目标端点按名池在图上精确匹配已入库实体），实体没齐边数会虚低。

## 3. 运行期：什么算正常、什么要动手

| 现象 | 判定 | 操作 |
| --- | --- | --- |
| 任务详情推进慢（大源每 ~26s 一批 2000 行） | 正常（见 §7 慢因） | 等 |
| 执行状态变 **TERMINATED**，详情/日志提到 history count / 事件数超限 | **设计内（㉞：Temporal 单执行 ~5.1 万事件硬限）** | 任务详情「重触发」→ 新执行从水位断点续跑（已完成环秒过）；大源每 ~300 万行写入会遇到一次，全程 5–8 次 |
| 日志出现「高水位退避 / 图库瞬态错误重发起」 | 正常（共享图库自愈防线在工作） | 不动手；仅当整链 FAILED 且错误文案不含 high watermark/RPC/Connection 字样才按失败排查 |
| worker 日志「Activity not found on completion … already completed」 | ㉞ 终杀后活动补完的尾巴，写入已落地 | 不当损伤 |
| T_EXTRACT_FAIL 审核队列出现 bankruptcy/forg_shareholder 行失败 | 基线同构（yft1 同样逐行失败） | 按业务口径处理，不是本轮回归 |
| 重触发后已跑完的环 written=0「秒过」 | 水位幂等重放（增量计数语义） | 对账一律看图侧计数，不看 written |

监控节奏建议 ≥30 分钟一巡：任务状态 + 大源行数/写入 + worker 重调度计数。

## 4. 验收对账锚点（跑完对照《绑定清单》§7 全表）

图侧点数一律用 `LOOKUP ON <tag> YIELD id(vertex) AS vid | YIELD COUNT(*)`（**SHOW STATS
不可信**）。关键锚点：Product **47,956**（VID=产品名哈希，点数=归一名去重数）；产业链
链 12 / 节点 1,261 / CHILD_OF 1,261 / HAS_NODE 1,261；News 108,052；COVERS_CHAIN 94,560；
BELONGS_TO_NODE ≈116,180；DOWNSTREAM_OF 0；零输出定案：ACTUAL_CONTROLLER_OF /
BENEFICIAL_OWNER_OF / PUBLISHED_IN(en) / FUNDED_BY(zh+en) / Keyword(en_project) /
HAS_OUTPUT 全部 0 属预期。抽查口径：VID 公式（report_{report_id} 等）、
source_system="gkx"、脚本未声明属性被 filtered() 丢弃是**基线同构**（先比对目录声明再报缺陷）。

## 5. 六个坑速查（部署前读一遍）

1. **⑰ LLM 校验不可复现**：前端存脚本必过 LLM 通道——不配 LLM key 最稳（自动降级）。
2. **⑭ querySql 被抹**：灌完每个 Schema 复查 querySql 未被编辑操作抹掉。
3. **㉔ TAG 静默建丢**：新建空间建 Schema 后逐个核对 DDL 状态；失败用「执行 DDL」补。
4. **㉝ 名字列索引**：§2⑦ 的 7 条 DDL 必做，否则 Person/Organization 环打爆共享图库。
5. **㉞ 事件硬限**：TERMINATED ≠ 故障，重触发续跑即可，全程会遇 5–8 次。
6. **㉟ graphd OOM 击杀链**：共享 trsgraph 容器（metad+graphd+storaged 同容器、无
   守护、Nebula 内存预算按宿主 125Gi 视图）——**匹配器脚本单条 IN 查询字面量必须
   ≤150**（仓库脚本已按此口径，自行改写时注意）；症状=写入侧 Connection refused /
   create session failed 洪峰 + 容器 `memory.events` 的 `oom_kill` 上涨。graphd 无
   状态，可 `docker exec -d` 原地拉起（flags 见《绑定清单》§8），但**先停本侧任务
   再拉**，否则重试洪峰 9s–3min 内再击杀。**注意：抽取之外，前端巡览也是 OOM
   向量**——图浏览分页对无索引大 tag 会回退 MATCH 全扫（日志指纹「LOOKUP 分页无
   索引…回退 MATCH 全扫」），巡览大空间尽量带过滤条件；graphd 死后同款原地拉起
   即可。

## 6. API 兜底

前端卡壳时可用等价 API（与《绑定清单》同仓库 `artifacts/gkx-prod-bindings/e2e_apply.py`
即全套自动化实现）：数据源 `POST /mysql-datasources`；实体/关系
`POST /schema-management/schemas/entities|relations`；脚本
`PUT /schemas/{id}/script`；绑定 `PUT /schemas/{id}/sources`（体为
`{"sources":[...]}`，**判 `success` 字段**——体形状错时 HTTP 仍 200、code=422，
按状态码判会静默丢写入，㊱）；链任务 `POST /workflow-system/jobs`（taskType=chain）；
触发 `POST /workflow-system/jobs/{id}/trigger`。响应统一 ApiResponse 包裹（取 `.data`）。

## 7. 慢因与耗时预期（部署者必读）

实测（环 11，dwd_patent→Keyword 源）：**~26.4s/批（2000 行）**，其中读源 ~1–3s（公网 +
S3 claim-check 中转）、脚本转换 ~1s、消歧召回 ~1–2s（索引后）、**写图 ~20s 为大头**——
每批 ~11,200 个实体逐条 `INSERT VERTEX`（经 trs-graph REST），叠加 ㉘ 写图限步调
（100 条/0.5s）与 4 活动槽并发上限，都是保护共享图库的主动限流。

放大因素：① 关键词/机构 5.6× 实体爆炸（3.28M 专利行 → 18.3M 实体）；② ㉞ 每执行 ~300 万
行写入即触顶，重触发循环有间隙；③ 外部库量为 yft1 样例的 100–3000 倍。总量算术：实体链
~6,000 万次实体写 ÷ ~400 条/s ≈ 40h+，**以天计是写入路径的物理结果，不是适配层回归**
（querySql/keyset 适配本身每批只占 ~1s）。

若需提速（平台改造项，按性价比排序）：~~写路径改批量多行 INSERT VERTEX（预计
5–10×）~~ **已落地（2026-10-14，提速项 ①）**：`write_records` 一批记录按属性列集分组
拼多行 `INSERT VERTEX/EDGE`（一条语句一次 HTTP 往返，行数上限 64/条、语句 2MB 兜底；
组内同目标去重保最后一条、组间按原始序，与逐条写语义等价；unknown column 整组剔列、
行级错误回退逐条定位坏行）。限步调随之改**按行计**：`SCHEMA_EXTRACT_WRITE_PACE_EVERY`
100→500（SLEEP 0.5 不变）≈ 单活动 1000 行/s 上限，压力窗再现时调小 every 即可、无需
回退批量；行数/条语句用 `SCHEMA_EXTRACT_WRITE_BATCH_ROWS`（默认 64）。实测：合成基准
2000 行/1.8s = **1113 行/s 单活动**（旧逐条路径被步调硬顶 200 行/s，**5.6×**；聚合
吞吐受 8 槽并发与消歧/召回等非写环节影响，低于该上限）；12 行小源全管道（读源→S3 中转
转换→消歧→批量写图→冲突探测）端到端秒级完成。未做：独占图库宿主 + 活动槽 4→16 +
再放宽限步调（3–4×，需团队决议）；㉞ continue-as-new（省循环空转 ~10–15%）；
稳定哈希 VID 的实体（Event 类）跳过同名召回。
