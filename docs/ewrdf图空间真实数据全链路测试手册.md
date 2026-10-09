# ewrdf 图空间真实数据全链路测试手册

> 2026-10-09 整理。目标:在公网门户 `https://edu.itic-sci.com/bkg_zpt` 所在的部署栈上,用独立的 `ewrdf` 图空间跑通「建 schema → 抽取 → 写图 → 人工审核 → 总览/检索可见」完整链路,不污染 dev2 等既有空间数据。
> 环境事实均为 2026-10-09 只读实测(SHOW SPACES / DESCRIBE / SELECT / docker inspect / bundle 指纹比对)。

---

## 0. 两个决定性前提

### 0.1 公网门户的实际承载是 dev2 栈,不是 8088"主栈"

| 项 | 公网 `/bkg_zpt` 实际承载(dev2 栈) | 容器名意义上的"主栈"(勿用) |
|---|---|---|
| web | `tech-kg-web-dev2`(8089 / 8091) | `tech-kg-web`(8088) |
| api | `tech-kg-api-dev2`(8002) | `tech-kg-api`(8001) |
| Temporal | `temporal-dev2:7233` | `temporal:7233`(独立实例) |
| 控制库 | `techkg_control@temporal-mysql-dev2` | `techkg_control@temporal-mysql` |
| worker | `tech-kg-temporal-worker-dev2`(队列 `tech-kg-workflows`) | **无任何 poller** |

- 证据:公网首页 bundle `index-3RRcFgqS.css` / `index-gGZtg9pL.js` 与 8089/8091 完全一致;8088 主栈的 `tech-kg-workflows` 队列经其 temporal-ui(8233)API 查询无 poller。
- **结论:全链路测试一律走公网门户(浏览器)或本机 8002 API。在 8088 栈下发抽取任务会永久挂起。**

### 0.2 ewrdf 空间已建好、已授权,不需要新建

- Nebula 实测:`ewrdf` 存在(SPACE ID 189),**0 tag / 0 edge 全空**,`vid_type=FIXED_STRING(64)`、partition=100、replica=1、utf8_bin —— vid 规格与 dev2 一致(注意 vid 上限 64 字符)。
- 2026-09-19 经平台 `POST /api/v1/graph-spaces` 正式创建(该接口 admin-only,请求体只有 `name`);`kg_graph_space_vector_db` 登记 `status=ready`。
- 控制库无任何 ewrdf 的 schema(`kg_schema_definition` 该空间 0 行)——是"已建未用"的干净空间。
- **user 241(`642903148@qq.com`)已于 2026-10-08 授权绑定 ewrdf**:用该账号登录门户即可直接切换,无需管理员操作。

---

## 1. 操作步骤(九步)

### ① 切换全局图空间到 ewrdf

登录 `https://edu.itic-sci.com/bkg_zpt/`,右上/顶部的全局图空间切换器选 `ewrdf`。
看不到该空间 = 登录账号没有授权,先到 `/configurations`(平台管理员)给账号绑定 ewrdf。

### ② 建 schema(当前空间必须是 ewrdf)

schema 管理 → 在 ewrdf 空间下分别建实体、关系 schema:

- **实体 schema 的属性表必须包含 `name`(string)**。建 TAG 时会自动建原生索引 `idx_{tag}_name`(string → `name(64)`)并 REBUILD:
  - CREATE INDEX 失败 = 建 schema 整体失败(会报错,修属性后重试);
  - REBUILD 失败仅告警,不影响(新写入自动进索引)。
  - 这个 name 索引是后续消歧同名召回、实体检索按名精确查找的**命脉**——没有它会出现"图里有但搜不到"。
- 关系 schema 只执行 `CREATE EDGE`,无索引,属正常,不需要处理。
- 建完空间后紧接着建 schema 偶发 DDL 传播延迟导致的 500,直接重试即可(内置 3 次重试)。

### ③ 上传抽取脚本(@step 风格)

两个 schema 各配脚本。**单步 transform 入口已下线**,必须:

```python
from kg_sdk import step

@step
def extract(payload):          # 函数名不能叫 transform / workflow
    rows = payload["rows"]     # 首步吃 rows
    return {
        "entities": [...], "edges": [...],
        "failures": [...], "pendingReview": [...],
    }
```

脚本经 API 上传后落共享 operator-rustfs 桶 `tech-kg-schema-scripts`,dev2 worker 取得到(2026-09-20 跨栈 S3 不一致已修复)。

### ④ 配真实数据源(`PUT /schema-management/schemas/{id}/sources`)

带 `pkColumn` / `timeColumn`。两条路:

1. **已有真实业务表**:注意时间水位与批量,避免全量扫共享库;
2. **最小真实造数**(推荐先跑通链路):共享测试表 `techkg_e2e_liz.review_widgets`,只插**自己前缀**的行:
   - 实体行:memo **不含** EDGE/POISON/PENDING;
   - 边行:memo **必须含 "EDGE"**(关系脚本只对含 EDGE 的行出边,漏了就 written=0 白跑);`from_id`/`to_id` 指向实体行 id;`update_time=NOW()` 过水位;
   - 经 docker mysql 操作中文必须 `--default-character-set=utf8mb4`,否则中文往返损坏;
   - 想触发 T_LINK 灰区审核案:同批插**同名多行**(同名无可比属性评分 = 0.80,恰落灰区 [0.65, 0.85)),一次可产多个案。

### ⑤ 触发抽取 job(graphSpace 必须显式带 ewrdf)

- UI:图谱构建页,单 schema 建 once job 触发;
- API:`POST /api/v1/workflow-system/jobs` body `{"taskType":"extract","schemaId":"...","graphSpace":"ewrdf"}` → `POST /api/v1/workflow-system/jobs/{id}/trigger`。

**为什么要显式带**:抽取写图空间解析优先级 = **job 的 graphSpace > schema 行绑定的 graph_space > worker 环境默认(dev2)**。不带参数时不报错,最坏情况静默写进 dev2。也**不要用** `/task-center/trigger` 全量扫(会触发别人的 schema)。

时间预期:共享图有负载波动波峰,小批量也可能跑几十分钟;dev2 worker 是单队列共享,遇到在飞任务需排队。

### ⑥ 验证执行与写图

- 执行状态以任务详情页/执行日志为准(控制库列表是懒刷新,别只看列表态;真实现态可看 Temporal)。
- 写图验证(只读,经图网关):

```bash
# SHOW SPACES / 统计
curl -s -X POST http://localhost:8090/api/v1/query \
  -H 'X-API-Key: ysukeg' -H 'X-Graph-Space: ewrdf' -H 'Content-Type: application/json' \
  -d '{"query":"SHOW STATS"}'

# 按 tag 查点(替换为你的 tag)
... -d '{"query":"MATCH (v:`YourTag`) RETURN v LIMIT 10"}'
```

- 写图后链路会自动 `SUBMIT JOB STATS`(空间级;失败仅告警 → 总览统计可能滞后一步,重进页面/等下次触发即恢复)。

### ⑦ 实体检索索引

- 实体检索是**全局单 collection `kg_entity`(default 库)按 `graph_space` 字段分区**,主键 `空间::vid`;不是每空间一个 collection。
- 新空间首次检索会报 **"图空间 ewrdf 尚未构建实体索引,请先在页面触发「重建索引」"** —— 属预期:
  - 正常路径:实体抽取收尾自动 `build_entity_index`(默认开启;依赖 m3e embedding 服务可用,否则整个执行会 FAILED);
  - 兜底:实体检索页面手动触发重建索引。ewrdf 从空起步,量小是秒级~分钟级,不是 dev2 全量那种 1-2 小时。
- 注意:建空间时自动建的同名 Milvus database 只是给脚本 milvus 选择器用的,与实体检索无关。

### ⑧ 人工审核与裁决

- 运营中心 → 人工审核队列,空间过滤 = ewrdf(队列已跟随全局空间切换;写图/重跑始终按 case 建案时烙定的空间,不受当前切换影响)。
- 预期出现两类案:
  - **实体对齐裁决(T_LINK)**:同名灰区/碰撞产生;
  - **抽取失败重跑(T_EXTRACT_FAIL)**:脚本 failures 逐行产生。
- 裁决(production submit,任何 action 终态都是 RESOLVED;REJECTED 仅废弃的旧直审通道):
  - `entityVerdict=merge`:真改目标节点属性;
  - `create`:按 `_incoming.vid` 落图 + 补写 `_pendingRelations` 暂存边;
  - `reject`:图零写入(驳回证据在 `GET /manual-reviews/production/{id}/audit-logs`)。
- C 类重跑:`rerun-extract-failures`,重跑工作流带原 case 空间;失败回滚 OPEN 的修复已在 dev2 栈镜像(2026-09-21 起不再卡 RERUNNING)。
- 裁决后该空间实体检索会自动做 Milvus 增量 upsert,无需手动重建。

### ⑨ 总览收口

`/bkg_zpt/overview` 切 ewrdf 空间核对:

- 图谱资产:实体/关系总量(去重口径);
- 今日新增:抽取出真实行(对象=名字或"起点 → 终点",来源=源表);
- 人工审核卡:top5 应显示 ewrdf 自己的案(不再被 dev2 的审测案霸占);
- 图谱构建任务卡:按空间过滤,只统计 ewrdf 的任务。

---

## 2. 风险与注意事项

| 风险 | 说明 | 对策 |
|---|---|---|
| 共享控制库未知清理者 | 2026-09-23 曾有演示 schema 13 分钟内被硬删、运行中 job 被取消(直连库操作,日志无痕) | 记好 schemaId/jobId;被删属环境问题,非链路问题 |
| 共享业务库 | `manual_review_case`、`review_widgets` 全栈共享,别人切到 ewrdf 也看得到你的案 | 造数只动自己前缀的行;别人(vb/vc/ex 等)的行别碰 |
| 图负载波动 | 共享 Nebula 有过载波,小批量抽取曾跑 41~53 分钟;波峰期总览诚实降级(卡片占位)属设计 | 错峰;验证部署/链路别拿波峰窗口的慢当故障 |
| vid 上限 | ewrdf vid=FIXED_STRING(64),超长 vid 写入会失败 | 造数行 id/vid 控制在 64 字符内 |
| 静默写错空间 | 抽取不带 graphSpace 时最坏落 worker 默认 dev2 | 触发时**永远显式带** `graphSpace:"ewrdf"` |
| T_DIRECT 写默认空间 | 旧通道 T_DIRECT 的 accept 在非 RBAC 部署下写 env 默认空间 | 现行抽取链不再产生 T_DIRECT,无需处理;遇到存量 T_DIRECT 案别在新空间测 accept |

---

## 3. 关键机制速查(代码依据,backend/ 相对路径)

- **建空间**:`POST /api/v1/graph-spaces`(admin 组,`biz/handler/graph_space.py`);后端 `CREATE SPACE IF NOT EXISTS`(vid_type=FIXED_STRING(64),partition/replica 取环境变量)+ 轮询等传播 + 写 `kg_user_graph_space` / `kg_graph_space_vector_db`。前端入口 `/configurations`(ConfigurationManagementView,仅 admin)。管理员空间列表读 Nebula SHOW SPACES(30s 缓存),普通用户读授权表。
- **抽取空间解析**:`service/temporal_workflows.py` `_extract_schema`:job payload `graphSpace` → schema 行 `graph_space`(经 `load_schema_extract_plan` 兜底)→ 都无则 `write_records` 落 env 默认空间。索引重建/失败建案/统计收尾均用同一空间。
- **schema DDL**:`service/schema_ddl.py`——实体建 TAG + `idx_{tag}_name`(仅当有 `name` 属性);关系只 CREATE EDGE;删 schema 先 DROP 索引再 DROP TAG。
- **实体检索**:`service/entity_search.py`——单 collection `kg_entity` 按 `graph_space` 分区;未建索引的空间首次检索报"尚未构建";reindex 优先 LOOKUP(吃标签原生索引),无索引标签回退 REST 全扫。
- **消歧召回**:`service/entity_disambiguation.py` `recall_same_name` 走 Nebula MATCH(tag 限定 `name IN [...]`),不是 Milvus;依赖 name 原生索引。
- **审核空间绑定**:`service/manual_review_production.py`——case 建案烙 `graph_space`(抽取运行的空间);队列 `graphSpace` 仅为查询过滤;T_LINK 裁决写图按 case/snapshot 的 `_graphSpace`。

---

## 4. 只读验证命令备查(本机执行)

```bash
# 图空间现状
curl -s -X POST http://localhost:8090/api/v1/query -H 'X-API-Key: ysukeg' \
  -H 'Content-Type: application/json' -d '{"query":"SHOW SPACES"}'

# ewrdf 内 tag/edge/统计
for q in 'SHOW TAGS' 'SHOW EDGES' 'SHOW STATS'; do
  curl -s -X POST http://localhost:8090/api/v1/query -H 'X-API-Key: ysukeg' \
    -H 'X-Graph-Space: ewrdf' -H 'Content-Type: application/json' -d "{\"query\":\"$q\"}"
done

# 控制库:ewrdf 的 schema(建完后应有行)
docker exec tech-kg-temporal-mysql-dev2 mysql -uroot -ptemporal \
  -e "SELECT id,name,kind,graph_space FROM techkg_control.kg_schema_definition WHERE graph_space='ewrdf';"

# 业务库:ewrdf 的审核案
docker exec tech-kg-mysql mysql -uroot -pgkx_element --default-character-set=utf8mb4 \
  -e "SELECT status,category,COUNT(*) FROM gkx_element.manual_review_case WHERE graph_space='ewrdf' GROUP BY status,category;"

# dev2 worker 健康/队列消费
docker ps --filter name=tech-kg-temporal-worker-dev2 --format '{{.Status}}'
```

> 安全边界:以上全部为只读查询。建 schema、传脚本、插数、触发 job、裁决均属写操作,在公网门户用账号操作,不通过脚本直写共享库。
