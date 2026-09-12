# 科技产业链点 TOP-N 事件关系：专家关联 ETL 与验收

接口：`POST /api/v1/kg-service/industry-node-top-events`

页面：业务服务 → 科技产业链点 TOP-N 事件关系。测试入参见 `docs/industry_chain_topn_test_parameters.md`。

标书要求：对链节点做事件影响力 TOP-N，并构建这些事件与**科技专家/人才**的关联。只有事件、没有 `experts`/`relations`，是当前测试环境的典型缺口。

本文按 2026-09-11 在 **trs-graph `test` 空间** 实操写成。跟着第 4～7 节做完：

- **只补图**：main / 旧 API 也能出专家（impact TOP 企业已有任职边）。
- **补图 + 本分支**：末位会换成瑞芯微年报，专家含励民，人数更多。

## 1. 结论（先看这里）

| 层 | 有没有问题 | 说明 |
| --- | --- | --- |
| 代码 | 有（本分支已改，非验收阻塞） | 任职边 6 种；扫描窗内有高管但 impact 进不了 TOP-N 时，用一条带专家的事件替换末位；窗外再补扫。 |
| 数据 | 有（test 已按第 5 节补完国内高管） | 服务**只读图**。补数前高管 Person / `EXECUTIVE_OF` 为 0。 |
| Schema | 有（`init-schema` 已补列） | test 的 Person 先按学者域建成（`name_zh`），没有 `name_cn`/`person_kind`。机构 ETL 直接 INSERT 会 400。 |
| ETL 映射 | 没有写错 VID | `dwd_org_executive_info` → Person → `EXECUTIVE_OF` 公式正确。 |

**只部署本分支、不补图：`experts=0`。** 服务不读 MySQL。  
**只补图、不部署本分支：页面已经能看到专家。** 补完国内高管后，impact TOP 企业（豪威等）也有 `EXECUTIVE_OF`，main 只查 TOP 事件企业也能命中。  
本分支额外把瑞芯微年报覆盖进末位（励民等），`max_orgs=10` 也能出专家。

2026-09-11 实测：

| 环境 | 结果 |
| --- | --- |
| 图 `test` 补数前 | `node_IC0007007`、瑞芯微 org、事件都在；励民 Person 无；`EXECUTIVE_OF` 入边 0 |
| 图 `test` 补数后 | 励民 Person 在；瑞芯微 `EXECUTIVE_OF` 入边 12 |
| 补数刚完成时 `tech-kg-api-main:8202` | 曾 `experts=0`（60s 缓存 / 当时 TOP 企业边尚未可读） |
| 补数生效后 `8202` / 本机 `8212`（旧代码）`max_orgs=50` | **`experts=3`**，姓名郑少波/范伟宏/陈向东；TOP 无瑞芯微 |
| **本分支服务直连 test**，`max_orgs=10/20/50` | **`experts=9`，`relations=9`，末位事件为瑞芯微年报，姓名含励民** |
| 本机页面 `127.0.0.1:5190` → 代理 `8212` | 本分支前端 + 旧后端，摘要可出「郑少波、范伟宏、陈向东」 |

## 2. 服务在图上读什么

`IndustryNodeTopEventsService` 直连 `infra.graph_db`（空间 = `TRS_GRAPH_SPACE`），不查 MySQL。

```
IndustryNode (node_{chain_node_id})
    ← BELONGS_TO_NODE(org, chain_score)  — 链上企业
    ← HAS_NODE                           — 所属产业链名
Organization
    → INVOLVED_IN → Event                — 财务/风险/招投标等
    → HAS_NEWS    → News                 — 资讯，event_type 记为 news
Person
    → EXECUTIVE_OF / LEGAL_REP_OF / ACTUAL_CONTROLLER_OF
    → BENEFICIAL_OWNER_OF / SHAREHOLDER_OF / AFFILIATED_WITH
    → Organization                       — 关联专家（对端必须是 Person）
```

排序：`impact_score`（事件类型权重 × 金额 × 时间新鲜度 × chain_score）→ TOP-N。  
专家：先查 TOP 事件企业入边；若全无专家，再查扫描窗内其余有事件的企业，仍无则探测窗外最多 30 家；用一条带专家的事件替换末位。机构股东（`SHAREHOLDER_OF` 对端是 Organization）丢弃。

`max_orgs` 默认 20，按 `chain_score` 截断。IC0007007 上有高管记录的主要是瑞芯微，约第 29。本分支在 `max_orgs=10/20/50` 下都能把瑞芯微年报补进末位。测试参数第四组仍建议 `max_orgs=50`，便于对上链上强度窗口。

## 3. 图上必须有的点 / 边

| 用途 | Tag / Edge | 源表（gkx_element，只读） | 谁写入 |
| --- | --- | --- | --- |
| 链节点 | `IndustryChain` / `IndustryNode`，`HAS_NODE` | `dwd_industry_chain_info` | `script/industry_chain_etl/load_industry_chain_graph.py` |
| 企业挂链 | `BELONGS_TO_NODE` | `dwd_org_industry_chain_dtl` | 同上；缺 org 点时先跑 `backfill_chain_org_nodes.py` 再灌边 |
| 企业点 | `Organization` `org_{org_id}` | `dwd_org_base_info` 等 | `python -m script.organization_entity_etl load` |
| 事件点 | `Event` | 年报/股市财务/融资/招聘/风险/破产/招投标等 | 同上 |
| 资讯点 | `News` | `dwd_org_important_news_info` | 同上 |
| 事件边 | `INVOLVED_IN` | 同上事件表 | `--relation event` |
| 资讯边 | `HAS_NEWS` | `dwd_org_important_news_info` | `--relation news` |
| **高管点（专家关键）** | `Person` | **`dwd_org_executive_info`**（海外 `dwd_forg_executive_info`） | `--table dwd_org_executive_info` |
| **高管边（专家关键）** | **`EXECUTIVE_OF`** | 同上 | `--relation executive` |
| 可选专家边 | `LEGAL_REP_OF` 等 / `AFFILIATED_WITH` | 法人/实控/受益/股东/学者任职 | 对应 `--relation`；`AFFILIATED_WITH` 来自学者域 |

关系 ETL **不建点**。源或目标 vid 不存在就 `skipped`，不会事后自动补。必须 **Person 先于 EXECUTIVE_OF**。

VID：

- 企业：`org_{org_id}`
- 高管：`person_{md5(NFKC-casefold("executive\|org_id\|姓名\|生日\|国籍"))}`
- 链节点：`node_{node_id}`（页面入参不要带 `node_` 前缀，如 `IC0007007`）

IC0007007 锚点：

- 瑞芯微 `org_id` = `dd27ebcec9c1cbe02d80704c721172f1`
- 励民（董事长/经理）→ `person_ede8636088bd9d2ddac9d774c165b3f6`

## 4. 推荐灌数顺序

统一在 `backend/` 下执行。`--space` 必须等于 API 的 `TRS_GRAPH_SPACE`（本地 `.env` 常为 `dev`，**线上 main 栈是 `test`**）。未传 `--space` 时脚本读环境变量，缺省 `dev`。源库只读 `gkx_element`，禁止写。

默认是 `--dry-run`，确认后再 `--write`。本机没有 `uv` 时用 `.venv/bin/python`。

```bash
cd backend

# 0) schema：共享空间 Person 若是学者字段，这一步会 ALTER 补 name_cn/person_kind
PYTHONPATH=. .venv/bin/python -m script.organization_entity_etl init-schema --space test

# 1) 机构域实体（只建点）。图上已有企业/事件时，最小补数见第 5 节，不必 --table all
PYTHONPATH=. .venv/bin/python -m script.organization_entity_etl load --full --write --space test

# 2) 机构域关系（只建边）
PYTHONPATH=. .venv/bin/python -m script.organization_relation_etl --relation event --write --space test
PYTHONPATH=. .venv/bin/python -m script.organization_relation_etl --relation news --write --space test
PYTHONPATH=. .venv/bin/python -m script.organization_relation_etl --relation executive --write --space test

# 3) 产业链节点 + 企业挂链
PYTHONPATH=. .venv/bin/python script/industry_chain_etl/load_industry_chain_graph.py
PYTHONPATH=. .venv/bin/python script/industry_chain_etl/backfill_chain_org_nodes.py

# 4) 若 3) 才补上缺失 org 点：再跑挂链/事件/高管边
PYTHONPATH=. .venv/bin/python -m script.organization_relation_etl --relation industry_node --write --space test
PYTHONPATH=. .venv/bin/python -m script.organization_relation_etl --relation event --write --space test
PYTHONPATH=. .venv/bin/python -m script.organization_relation_etl --relation executive --write --space test
```

全量关系可用 `--relation all`。总顺序见 `docs/rebuild_graph_data_scripts.md`。

## 5. 图上已有事件、只缺专家时的最小补数

test 的典型状态：链节点、企业、`INVOLVED_IN`/`HAS_NEWS` 都在；学者 Person 也可能在；**高管 Person 和 `EXECUTIVE_OF` 为 0**。不要全量重灌。

**必须先 `init-schema`。** 否则下一步 INSERT Person 400：`Unknown column 'name_cn' in schema`。

```bash
cd backend

# 0) 给学者域 Person 补机构字段（幂等；已有列会跳过）
PYTHONPATH=. .venv/bin/python -m script.organization_entity_etl init-schema --space test

# 1) 先点。2026-09-11：queried=5600 valid=5500 written=5481 failed=0（100 行虚拟源跳过）
PYTHONPATH=. .venv/bin/python -m script.organization_entity_etl load \
  --table dwd_org_executive_info --full --write --space test

# 2) 后边。国内：written=5500 source_missing=0；海外表因未灌 Person 会 source_missing，不影响 IC0007007
PYTHONPATH=. .venv/bin/python -m script.organization_relation_etl \
  --relation executive --write --space test
```

海外高管若也要：先 `--table dwd_forg_executive_info`，再跑同一 `--relation executive`。

Nebula ALTER TAG 后偶发要等 schema 传播；`init-schema` 里已有短重试。若仍 400，等数秒再跑 entity load。

## 6. 灌完怎么确认图上有专家

用与 API 相同的 space：

1. `get_node("node_IC0007007")` 非空（集成电路设计）。
2. `get_node("org_dd27ebcec9c1cbe02d80704c721172f1")` 非空（瑞芯微电子股份有限公司）。
3. `get_node("person_ede8636088bd9d2ddac9d774c165b3f6")` 非空，`name_cn=励民`。
4. 对该 org `get_node_edges(..., direction="in", edge_type="EXECUTIVE_OF")` **> 0**（补数后为 12）。
5. 瑞芯微另有 `INVOLVED_IN` / `HAS_NEWS`（否则补进 TOP 也没有事件可展示）。
6. 关系日志：国内 `source_missing=0`。`skipped` 很大且 `valid=0` → Person 没进这个 space，或 `--space` 与 API 不一致。

实体走 nGQL `INSERT VERTEX`，关系走 `INSERT EDGE`，**不要**用 `merge_node`。

本机脚本连 `TRS_GRAPH_BASE_URL`（`.env` 为 `http://localhost:8090`），与 `tech-kg-api-main` 的 `host.docker.internal:8090` 是同一套图。改 space 时两边一起改。

## 7. 接口 / 页面怎么看到效果

1. 进程 `TRS_GRAPH_SPACE` 必须等于刚灌的空间（线上 main 栈 / 本机 8212 都是 `test`）。
2. **只验「有没有专家」**：补完第 5 节后，现网 `8202`/`8290` 或本机已在跑的旧 API 即可，不必等本分支镜像。
3. **要看到瑞芯微 / 励民、或 `max_orgs=10` 也出专家**：部署本分支后端；前端用本分支，摘要才会把姓名写进「关联专家」。
4. 调接口或页面：

```json
{
  "chain_node_id": "IC0007007",
  "top_n": 10,
  "max_orgs": 50
}
```

本分支默认 `max_orgs=20`（甚至 10）也会因覆盖替换出现专家。第四组 `max_orgs=50` 便于对扫描窗口；旧代码必须把窗口开到能扫到有任职边的 TOP 企业。

5. 验收：

| 位置 | 只补图（main / 8212） | 补图 + 本分支 |
| --- | --- | --- |
| 响应 `experts` | **≥ 1 即过**（实测 3） | 实测 9 |
| 响应 `relations` | 非空；郑少波/范伟宏/陈向东 | 另含励民/刘越/王海闽等；有瑞芯微 |
| `top_events` 末位 | impact TOP，无瑞芯微 | 瑞芯微 `annual_finance`（覆盖替换） |
| 结果图 | 事件节点连到专家 | 同左，且含瑞芯微事件 |
| 摘要「关联专家」 | 「郑少波、范伟宏、陈向东 3 人」 | 「…励民 等 9 人」 |

结果有 60s 进程内缓存。刚灌完图若仍是 0，等一分钟或重启 api 再查。

不经过 HTTP、直接验服务：

```bash
cd backend
PYTHONPATH=. TRS_GRAPH_SPACE=test .venv/bin/python - <<'PY'
import asyncio, os, importlib
os.environ["TRS_GRAPH_SPACE"] = "test"
import service.industry_node_top_events_business as m
importlib.reload(m)
from biz.schemas.industry_node_top_events_business import IndustryNodeTopEventsRequest
async def main():
    m._result_cache.clear()
    resp = await m.IndustryNodeTopEventsService().run(
        IndustryNodeTopEventsRequest(chain_node_id="IC0007007", top_n=10, max_orgs=50)
    )
    print(resp.experts, [r.expert_name for r in resp.relations[:5]])
asyncio.run(main())
PY
```

本地再起 **当前代码** 的 FastAPI 时：`.env` 里只有 `AUTH_ENABLED=false` **不够**，受保护接口会 503「认证服务未启用」。需要进程环境同时有：

```bash
APP_ENV=local AUTH_ALLOW_INSECURE_DEV_CONTEXT=true AUTH_ENABLED=false TRS_GRAPH_SPACE=test
```

或保持鉴权走登录。不要把这两个开关写进仓库 `.env`。

本机已有、且 `AUTH_ENABLED=false` 已放行的旧进程（例如 8212，2026-09-08 起的、早于这道鉴权闸）可以直接拿来看页面，不必再开 insecure 开关。2026-09-11 验收用的就是：

- 前端：`VITE_API_TARGET=http://127.0.0.1:8212`，`vite --host 127.0.0.1 --port 5190 --strictPort`
- 页面：`http://127.0.0.1:5190/#/industry-chain-event`

## 8. 常见失败（含 2026-09-11 实操）

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| entity load Person 批处理 400，`Unknown column 'name_cn'` | test Person 是学者 schema（`name_zh`），无 `name_cn`/`person_kind`。`CREATE TAG IF NOT EXISTS` 不加列 | **先** `init-schema --space test`（本分支 reconcile 会 ALTER 补机构字段），再 load |
| 有事件、`experts=0`，图上高管边也是 0 | 没灌高管或先边后点被 skip | 第 5 节：先点后边 |
| 图上已有高管边，**刚打 8202 仍 experts=0** | 进程内 60s 缓存，或 TOP 企业边当时还不可读 | 等 TTL / 重启后再打；补数生效后旧代码也会 `experts=3` |
| 旧代码有专家、但没有励民/瑞芯微 | main 只查 TOP 事件企业；瑞芯微 impact 进不了前 10 | **部署本分支**才会覆盖替换末位 |
| 本分支 `max_orgs=50` 曾仍为 0（补数后、覆盖替换落地前） | 旧补扫只探测**窗外**；瑞芯微在窗内但排不进 TOP-10 | 本分支改为：TOP 无专家时先查窗内其余有事件企业，再查窗外 |
| 补了边仍为 0 | 先跑 relation、当时点不存在 | 先 entity 再 relation；skip 不会自动重放 |
| 本地有、页面没有 | `--space` / `TRS_GRAPH_SPACE` 不一致（`dev` vs `test`） | 脚本加 `--space test`，API 环境变量相同 |
| 只部署代码不灌数 | 服务不读 MySQL | 必须灌图 |
| `max_orgs=20` 对不上瑞芯微（旧代码） | 按 chain_score 截在约第 20 | 本分支会补扫/覆盖；或第四组 `max_orgs=50` |
| relation 国内 OK、海外 `source_missing` 上千 | 未灌 `dwd_forg_executive_info` Person | IC0007007 不需要；要海外时先灌海外实体 |
| 股东边很多但专家仍 0 | `SHAREHOLDER_OF` 对端是机构 | 正常，服务丢掉；要 Person |
| 本地 uvicorn 503 认证未启用 | 当前代码 `AUTH_ENABLED=false` 且未开 insecure dev | 复用已放行的旧进程（8212），或 `APP_ENV=local AUTH_ALLOW_INSECURE_DEV_CONTEXT=true` |
| 页面摘要仍是「0 人」/静态 18 人 | 前端不是本分支，或代理打到未补数/503 的 API | 本分支摘要用 `relations[].expert_name`；确认 `VITE_API_TARGET` 指向有数据的后端 |
| 刚灌完仍旧结果 | 60s 结果缓存 | 等 TTL 或重启 api |

不要对 `gkx_element` / 生产 MySQL 做写操作。不要对 `prod` 图空间做探测或灌数，除非另行授权。

## 9. 保证页面有效果的检查清单

按顺序打勾，缺任何一项测试老师都会说「没有专家关联」：

1. [ ] `init-schema --space test`（Person 有 `name_cn`）
2. [ ] `organization_entity_etl load --table dwd_org_executive_info --full --write --space test`（`failed=0`）
3. [ ] `organization_relation_etl --relation executive --write --space test`（国内 `written>0`，`source_missing=0`）
4. [ ] 瑞芯微 `EXECUTIVE_OF` 入边 > 0，励民 `get_node` 非空
5. [ ] API `TRS_GRAPH_SPACE=test`。只验有专家：main/8212 即可；要励民/瑞芯微：部署本分支
6. [ ] 前端是本分支（摘要展示姓名），`VITE_API_TARGET` 指向上一步的 API
7. [ ] 页面执行 `chain_node_id=IC0007007`（建议 `max_orgs=50`）
8. [ ] `experts>=1`，摘要出现姓名，图上事件连到专家
