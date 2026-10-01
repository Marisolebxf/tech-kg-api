# yunfei_test 图空间全量重建手册（dev 口径 · 数据整理与装载）

> 快照日期：2026-09-30。本手册只写「怎么把数据整理好」：从 gkx_element 源数据出发，
> 把一个全新图空间装载到与生产 dev 空间**同口径**的全量状态（本轮实例 `yunfei_test_1`，
> 方法适用于任何新空间）。步骤：装数 → 清场 → 建空间与预建 schema → 平台链 → 离线域 → 验证。
>
> 本文不含脚本全文与逐 Schema 明细：45 个平台抽取脚本、73 张表 DDL、机器可读 manifest
> 见上一版自包含文档（`git show 5276409f:backend/docs/yunfei_test全量重建文档.md`）；
> 离线域脚本全部在仓库 `backend/script/` 下，以仓库为准。

## 0. 口径与总览

**dev 口径** = dev 空间的数据构成：两路写入的并集，全部读 gkx_element 现行数据。

1. **平台抽取链**（45 个脚本 = 16 实体 + 29 关系，任务中心 chain 任务逐环抽取）
2. **仓库离线域脚本**：学者域 → 机构域 → 论文域 → 论文桩对齐（SAME_AS）

不在还原范围（dev 有、重建空间预期没有，见 §7 残差表）：fixture 专有边
（APPLIED_BY/INVENTED_BY/HAS_OUTPUT 等）、九大业务模块自建边（EMPLOYED_BY/COLLEAGUE/ALUMNI）。

| # | 步骤 | 产物 | 本轮实测 |
| --- | --- | --- | --- |
| 1 | MySQL 装数 + 注册数据源 | 源库 `gkx_element_yft1`（73 张 dwd_* 表） | ~10 min |
| 2 | 清场（图空间 / 向量库 / 水位） | 干净起点 | ~5 min |
| 3 | 建图空间 + 预建统一 schema | 全可空 TAG/EDGE + name 索引 | ~5 min |
| 4 | 平台三链：还原-实体 → 关系A → 关系B | 平台侧点边 | 34 min |
| 5 | 离线域 ETL：学者 → 机构 → 论文 → 桩对齐 | 离线侧点边 + SAME_AS | ~1 h |
| 6 | 验证对账 | 与 dev 一致（残差全部可归因） | ~10 min |

## 1. 前置条件与执行姿势

- yunfei3 栈在跑（api + temporal-worker + web）。本手册命令全部在 **api 容器内**执行：

  ```bash
  docker exec -w /app -e PYTHONPATH=/app tech-kg-api-yunfei3 .venv/bin/python <脚本>
  ```

- 容器内 `/app` 是**镜像拷贝**：改过仓库脚本必须先
  `docker cp backend/script/xxx.py tech-kg-api-yunfei3:/app/script/` 再跑，否则跑的是旧代码。
- 目标图空间经 env 传给离线脚本：`-e TRS_GRAPH_SPACE=<空间名>`；Milvus 统一
  `-e MILVUS_URI=http://milvus:19530`。
- gkx / gkx_element 会话**只读**，绝不写源库。

## 2. MySQL 装数与数据源注册（平台侧源库）

平台抽取链不直连 vendor 库，读「注册数据源」指向的库。装数 = 把 gkx_element 的
73 张 dwd_* 表（清单见 §8）原样复制到**同一 MySQL 实例**的独立库（本轮 `gkx_element_yft1`）：

```bash
# 宿主机执行（同实例跨库复制，免导出文件；mysqldump 导入等效）
mysql -h127.0.0.1 -P30306 -uroot -p -e 'CREATE DATABASE IF NOT EXISTS gkx_element_yft1 DEFAULT CHARACTER SET utf8mb4'
mysql -h127.0.0.1 -P30306 -uroot -p -e '
  CREATE TABLE gkx_element_yft1.dwd_xxx LIKE gkx_element.dwd_xxx;
  INSERT INTO gkx_element_yft1.dwd_xxx SELECT * FROM gkx_element.dwd_xxx;'   -- 逐表 ×73
```

注册数据源（管理端「配置管理 → MySQL 数据源」，等价 `POST /api/v1/mysql-datasource`）：

| 字段 | 本轮值 |
| --- | --- |
| 名称 | `gkx-element-yunfei1` |
| 主机 / 端口 | `host.docker.internal` / `30306` |
| 默认库 | `gkx_element_yft1` |

> 链任务 payload 里的 `mysqlDatasourceId` / `mysqlDatabase` 引用这两个值——**复用已建链任务时库名与数据源不能换**，否则链读不到表。密码不入本文档。

## 3. 清场（对已有空间重跑时必做）

三处残留不清，新数据会叠旧数据、或链首跑读 0 行：

```python
# 容器内 /tmp/ 执行（骨架，连接走 infra 单例）
from infra.graph_db import get_trs_graph_client
from infra.milvus import get_milvus_client
from infra.mysql import session_scope

SPACE = 'yunfei_test_1'
# ① 图空间
get_trs_graph_client().execute_write(f'DROP SPACE IF EXISTS `{SPACE}`')
# ② 向量库：Milvus 同名库（含集合）+ 映射行
mc = get_milvus_client()
if SPACE in mc.list_databases():
    for col in mc.list_collections(db_name=SPACE):
        mc.drop_collection(col, db_name=SPACE)
    mc.drop_database(SPACE)
from db_model.platform_governance import GraphSpaceVectorDatabase
with session_scope() as s:
    for r in s.query(GraphSpaceVectorDatabase).filter_by(graph_space=SPACE):
        s.delete(r)
# ③ 抽取水位（业务库，不是控制库）
from db_model.script_watermark import ScriptWatermark
from service.schema_extraction import extract_watermark_definition_ids
from sqlalchemy import select, text
with session_scope() as s:
    keys = [r[0] for r in s.execute(text(
        'SELECT schema_key FROM kg_schema_definition WHERE graph_space=:sp'), {'sp': SPACE})]
    ids = set()
    for k in keys:
        ids.update(extract_watermark_definition_ids(k))
    rows = s.execute(select(ScriptWatermark).where(ScriptWatermark.definition_id.in_(ids))).scalars().all()
    for r in rows:
        s.delete(r)
    print(f'水位清除 {len(rows)} 行 / {len(ids)} definition_id')   # 本轮 151 行 / 49 id
```

要点：

- **水位跨图空间共享**：`kg_script_watermark` 按 `schema-extract-{schema_key}` 键存取，
  不区分空间。旧空间跑过的链会把游标顶到头，新空间首跑直接读 0 行。
- 平台服务之后可能自动重建同名**空** Milvus 库（无集合、无映射行），无害。
- DROP SPACE 后确认 `SHOW SPACES` 里确实消失再继续（有传播延迟）。

## 4. 建图空间与预建统一 schema（关键口径，顺序不能错）

**为什么必须预建**：平台建 Schema 会把 required 属性建成 NOT NULL（`service/schema_ddl.py`
build_create_ddl），而离线域用 nGQL `INSERT VERTEX/EDGE` 整行写入，不逐列填
id/name/create_time —— 撞 NOT NULL 整域 400「The not null field doesn't have default value」。
Nebula 改不了已有列的 NOT NULL，唯一正确顺序：**先把两路 schema 的并集以全可空口径建好，
之后平台/离线各自的建表语句（都是 CREATE IF NOT EXISTS）全部 no-op**。

**预建来源直接用 dev**（本轮部分列来自旧文档 manifest，出现过 SAME_AS.confidence 被建成
double 而 dev 实际是 string 的漂移——从 dev 现网 DDL 预建天然无此问题）：

```bash
# ① 平台建空间（图空间管理）：vid FIXED_STRING(256)。机构域长 vid 超 64 会被拒
#    （2026-09-30 起平台默认即 256）；老平台须升级或手工 CREATE SPACE ... vid_type=FIXED_STRING(256)
```

```python
# ② 预建：容器内 /tmp/ 执行。dev 全部 TAG/EDGE 的 DDL 去 NOT NULL 后在目标空间重建 + name 索引
import re, time
from infra.graph_db import get_trs_graph_client
from infra.graph_db.client import TRSGraphClient

SRC, DST = 'dev', 'yunfei_test_1'
base = get_trs_graph_client()
src = TRSGraphClient(base._settings.model_copy(update={'space': SRC})); src.connect()
dst = TRSGraphClient(base._settings.model_copy(update={'space': DST})); dst.connect()

def w(stmt):
    for i in range(5):
        try:
            dst.execute_write(stmt); return
        except Exception as e:
            if i == 4: raise
            print('  重试:', str(e)[:80]); time.sleep(1 + i)

for kw, col in (('TAG', 'Create Tag'), ('EDGE', 'Create Edge')):
    names = [r.get('Name') for r in src.execute_read(f'SHOW {kw}S').records if isinstance(r, dict)]
    for n in names:
        ddl = src.execute_read(f'SHOW CREATE {kw} `{n}`').records[0].get(col)
        ddl = re.sub(r'\s+NOT NULL', '', ddl).replace(f'CREATE {kw} ', f'CREATE {kw} IF NOT EXISTS ')
        w(f'USE {DST}; {ddl}')
        if kw == 'TAG':
            ft = {r.get('Field'): r.get('Type')
                  for r in src.execute_read(f'DESCRIBE TAG `{n}`').records if isinstance(r, dict)}
            t = ft.get('name') or ''
            if t == 'string' or t.startswith('fixed_string'):
                idx = f'idx_{n.lower()}_name'
                spec = 'name(64)' if t == 'string' else 'name'
                w(f'USE {DST}; CREATE TAG INDEX IF NOT EXISTS `{idx}` ON `{n}`({spec})')
                for _ in range(5):
                    try:
                        dst.execute_query(f'USE {DST}; REBUILD TAG INDEX `{idx}`'); break
                    except Exception:
                        time.sleep(2)
```

核对：`SHOW TAGS / SHOW EDGES / SHOW TAG INDEXES`。dev 全集 = TAG 20 / EDGE 38
（其中 4 TAG、5 EDGE 是平台历史 0 计数残留，建了无害、保证清单与 dev 完全一致；
本轮按 manifest 只预建了 16 TAG / 33 EDGE，数据结果相同）。

**预建后各域自带的 init-schema / reconcile 全部 no-op**——包括机构域的
`reconcile_existing_schema`（ALTER ADD）与论文域缺列问题（本轮曾需手工 ALTER 补
CITED_BY.ingest_batch/ingest_time，从 dev 预建后不存在此问题）。

## 5. 平台三链

任务中心三条 chain 任务（已存在则直接触发，`POST /api/v1/workflow-system/jobs/{id}/trigger`；
新建：taskType=chain、batchSize=500、选数据源与图空间）。**顺序执行，实体链必须先完**
（关系脚本读图内既有实体做端点匹配）：

| 链 | 环序（每环 = 一个 Schema 抽取） | 本轮终态 |
| --- | --- | --- |
| 还原-实体（16 环） | DataSource → Event → IndustryChain → IndustryNode → Journal → Keyword → News → Organization → Paper → Patent → PatentFamily → Person → Product → Project → Report → OrganizationBase | ABNORMAL（1077 条失败记录） |
| 还原-关系A（15 环） | ACQUIRES → ACTUAL_CONTROLLER_OF → AFFILIATED_WITH → AUTHORED_BY → BELONGS_TO_NODE → BENEFICIAL_OWNER_OF → CHILD_OF → CITES → COAUTHOR_WITH → COVERS_CHAIN → DOWNSTREAM_OF → EXECUTIVE_OF → FUNDED_BY → HAS_KEYWORD → HAS_NEWS | ABNORMAL（1077） |
| 还原-关系B（14 环） | HAS_NODE → HAS_OUTPUT → HAS_PARTICIPANT → INVESTS_IN → INVOLVED_IN → LEADS → LEGAL_REP_OF → MEMBER_OF_FAMILY → PRODUCES → PUBLISHED_IN → REFERENCED_BY → SHAREHOLDER_OF → SUBSIDIARY_OF → STUDIED_AT | ABNORMAL（36520） |

**ABNORMAL 是预期终态**：源数据行级失败（坏行/同名待审）转人工审核，不中断抽取，环本身
完成。1077 = `dwd_forg_act_contro_info` 的 entity_type 异常行（50 行「测试数据」残留 + 1027 行
NULL）；36520 = forg_shareholder/subsidiary/实控表按同口径转 T_EXTRACT_FAIL 的行，这些行本就
不产出边。链内**硬失败**（缺表/VID 超长/脚本异常）才是 FAILED，须排查后重触发。

> 本栈 compose 关闭了随环索引重建（`SCHEMA_EXTRACT_BUILD_INDEX=0`，防共享 Nebula 内存
> 顶过水位）。三链结束后如需实体检索，用管理端点统一重建一次实体索引。

## 6. 离线域 ETL（域序固定：学者 → 机构 → 论文 → 桩对齐）

以下命令为实跑原样（`$D` 为 §1 的 docker exec 前缀 + `-e TRS_GRAPH_SPACE=yunfei_test_1
-e MILVUS_URI=http://milvus:19530`）。

**域1 学者域**（Person/AUTHORED_BY/COAUTHOR_WITH/AFFILIATED_WITH + scholar_person 向量集合）：

```bash
$D script/rebuild_scholar_graph.py --graph-space yunfei_test_1 --stages schema,entities,relations,milvus,align
```

- schema 阶段预建后 no-op；milvus 阶段需 §6.1 运行时依赖；
- align 阶段在本栈无 `organization` 向量集合，日志 skip 属预期（dev 同样未产出）。

**域2 机构域**（Organization/organization_base 混入/Event/风险事件边等）：

```bash
docker exec -w /app -e PYTHONPATH=/app tech-kg-api-yunfei3 sh -c '
  .venv/bin/python -m script.organization_entity_etl init-schema --space yunfei_test_1 && \
  .venv/bin/python -m script.organization_entity_etl load --table all --full --write --space yunfei_test_1 && \
  .venv/bin/python -m script.organization_relation_etl --relation all --write --space yunfei_test_1'
```

- `init-schema` 后 DDL 传播 ~15 s，紧接 `load` 偶发「Unknown tag」属传播延迟，重跑即过。

**域3 论文域**（Paper/Journal/Report + CITES/CITED_BY/RELATED_TO/HAS_KEYWORD/REFERENCED_BY）：

```bash
$D script/init_paper_journal_schema.py          # 预建后 no-op，跑一遍兜底
$D script/load_paper_journal_graph.py           # 实体 + PUBLISHED_IN/AUTHORED_BY 等
$D script/paper_journal_relation/load_paper_relation.py    # 关系边 + paper_ref/rel/rp 桩
$D script/paper_journal_relation/backfill_edge_confidence.py  # RELATED_TO=0.7 / REFERENCED_BY=0.8
$D script/paper_journal_relation/attach_provenance.py      # organization_base 溯源混入
```

**域4 论文桩对齐**（SAME_AS 的唯一来源，dev 259 条全部由此产出）：

```bash
$D -m script.paper_milvus.align_paper_relations
```

- 依赖 Milvus `paper` 集合（doi→vid 注册表，`build_paper_journal_milvus_index` 产物，
  4000 行 = zh+en 论文）；
- 写入前提：SAME_AS 边 schema 与 dev 一致（`confidence` 是 **string**）。§4 从 dev 预建
  天然满足；若被建成 double，插入 `'1.0000'` 报 400 data type——DROP EDGE 后按 dev DDL 重建。

**域5 学者消歧**（可选，验证口径用）：

```bash
$D script/rebuild_scholar_graph.py --graph-space yunfei_test_1 --stages dedupe
```

- dev 实测高置信候选 0（SAME_AS 全来自域4），两空间一致，跑与不跑不影响计数。

### 6.1 消歧 / milvus 阶段运行时依赖（镜像外，容器重建后需重装）

```bash
# venv 无 pip：root + uv + 独立 cache + 国内源
docker exec -u 0 -e UV_CACHE_DIR=/tmp/uv-cache -e UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
  tech-kg-api-yunfei3 uv pip install --python /app/.venv/bin/python nltk jieba
# 中文停用词：nltk.download 出网被限（raw.githubusercontent/gitee 均不可达），走 jsdelivr 静态包；
# zip 直接被 nltk 识别，无需解压
curl -sL https://cdn.jsdelivr.net/gh/nltk/nltk_data@gh-pages/packages/corpora/stopwords.zip -o /tmp/sw.zip
docker exec tech-kg-api-yunfei3 mkdir -p /usr/local/share/nltk_data/corpora
docker cp /tmp/sw.zip tech-kg-api-yunfei3:/usr/local/share/nltk_data/corpora/stopwords.zip
```

m3e 模型经 hf-mirror.com 自动下载，无需处理。生产化建议：`uv sync --extra milvus` 覆盖
nltk/jieba，nltk_data 随镜像或卷预置。

## 7. 验证基准与残差归因

对账方法：两空间各 `SUBMIT JOB STATS` 等 `SHOW STATS` 稳定后逐 TAG/EDGE 比计数，
基准 = **dev 现网计数**（dev 仍在被写入，允许 ±1 级抖动）。本轮终态（2026-09-30）：

| 分组 | 项目（yft_1 vs dev） | 处置 |
| --- | --- | --- |
| **全等 / 容差内**（差值 ≤ ±10） | DataSource 39、Journal 2134、PatentFamily 1999、Project 4005、Report 3000、IndustryNode 180、CHILD_OF 174、DOWNSTREAM_OF 4、HAS_NODE 180、MEMBER_OF_FAMILY 2000、PUBLISHED_IN 4081、COAUTHOR_WITH 156144、RELATED_TO 79320(≈79319)、SAME_AS 259、REFERENCED_BY 12806(≈12808)、FUNDED_BY 140(≈150)、COVERS_CHAIN 476(≈479)、STUDIED_AT 92(≈96) | 过账 |
| **源数据年代差**（dev 自 8 月起累积，现行 gkx_element 已无那些行，不可复现） | Organization −2428、Person −401、Paper −74、News −103、Patent −10、Product −1、IndustryChain −1、AFFILIATED_WITH −1502、HAS_KEYWORD −19212、AUTHORED_BY −162（后三项为缺 Org/Person 端点的级联） | 接受（以当前源为准） |
| **fixture / 业务边**（不在还原范围） | APPLIED_BY −80、INVENTED_BY −20、HAS_OUTPUT −38、OWNED_BY −1、ALUMNI −55、COLLEAGUE −25、EMPLOYED_BY 全缺（边类型 dev 与重建空间均未建，见 §7.1；STUDIED_AT 中 4 条同源） | 预期缺失 |
| **yft_1 更全**（当前源比 dev 历史抽取更全，保留） | CITES +171874、INVOLVED_IN +24637、EXECUTIVE_OF +7041、BENEFICIAL_OWNER_OF +6284、Keyword +7861、Event +4202、organization_base +7950、INVESTS_IN +4083、SHAREHOLDER_OF +2307、BELONGS_TO_NODE +2562、CITED_BY +2559、PRODUCES +2046、LEGAL_REP_OF +1045、HAS_NEWS +813、ACQUIRES +853、HAS_PARTICIPANT +162、SUBSIDIARY_OF +118、LEADS +22、ACTUAL_CONTROLLER_OF +50 | 保留 |
| **平台链专属**（dev 未经历过该平台环） | OrganizationBase tag 61652（dev 无此 tag） | 预期多出 |

> 上表「全等」列的数字为本轮实测快照；重跑时逐项对 dev 现值比即可，落入上述任一分组
> 即视为过账，不必逐项追平绝对值。

### 7.1 九大业务模块可用性验证（2026-09-30 实测）

九模块的数据面走 env 冻结空间（运行中 api 容器恒为 dev），验证不动 compose：容器内
`docker exec -e TRS_GRAPH_SPACE=<空间>` 起新进程，用 `httpx.AsyncClient(transport=
httpx.ASGITransport(app=main.app))` 进程内打 `/api/v1` 路由（加 `-e PREWARM_BUSINESS=false`
免预热干扰）。测试实体必须从图内真实关系挑——如 COAUTHOR_WITH 对不含共同 Paper 邻居，
测「两点成果/论文合作」要挑同一 `Paper -AUTHORED_BY-> 两人` 的对，否则得到的是真空而非缺数。

| 模块 | 结果 | 实测样本 |
| --- | --- | --- |
| 学者直接关系 | ✅ | 王建宇↔潘建伟 1 条直接关系（COAUTHOR_WITH） |
| 节点间接关系 | ✅ | 王甫园：间接节点 92 / 路径 228（接口限制 `relation_types` 单次 ≤1 项） |
| 两点成果 | ✅ | 王甫园↔王开泳 共同论文 1 篇 |
| 学者同事 | ✅ | 杨彬↔薛宁 金能科技任职时间重叠 1 条（AFFILIATED_WITH 边上 work_experience_date） |
| 学者校友 | ✅ | 裴诗雅↔熊若兰 北京大学同校（STUDIED_AT 推得） |
| 论文合作 | ✅ | 王甫园↔王开泳：合作论文 1 篇、合作频次 1、学术影响力 10.7、核心合作者 4（数据在 `structuredResult` 嵌套层） |
| 企业关联 | ⚠️ | 查询空；构建链路本身可用（见下） |
| 产业链事件 | ✅ | IC0007005（半导体设备）top5 事件 + 15 专家 + 3 企业 |
| 产业链全景 | ✅ | 集成电路 4 层（核心技术/…） |

探针解读注意（首轮曾因此误报两个模块空）：时间参数本栈要求 `YYYY-MM-DD`（`YYYY-MM` 422）；
模块 2/6 的实体关系数据在响应的 `structuredResult` 嵌套层，只扫顶层列表字段会误判为空。

- **论文合作**：`PAPER_COOPERATED_WITH` 是可选的**预计算缓存边**，两空间均未建
  （traversal 400 被吞、仅留 stderr 日志噪音），主路径走子图共同论文解析，不依赖该边。
- **企业关联**（唯一空模块）：`EMPLOYED_BY` 边类型 dev 与重建空间均未初始化
  （`DESCRIBE EDGE` 双双 EdgeNotFound），属 §0「不在还原范围」的业务边，非重建缺数。
  实测临时 `CREATE EDGE EMPLOYED_BY`（5 属性：relation_type/role/start_date/end_date/source）
  后 `build` 正常——`effective=True`、写出并返回 1 条关系；要让模块可用需显式建边类型
  （业务动作）。`/kg-service/key-enterprise-relation` 查询走 2 跳子图解析，构建后仍解析
  0 条，未深挖。测试后已删边 + `DROP EDGE` 还原。

## 8. 源表清单（73 张，括号为装数后行数核对）

```text
dwd_bid_base_out(100) dwd_bid_purchase_agency_out(100) dwd_bid_target_item_out(100) dwd_bid_win_candidate_out(100)
dwd_en_author(12977) dwd_en_journal(2126) dwd_en_paper(2000) dwd_en_paper_citation(527)
dwd_en_paper_classification(2000) dwd_en_paper_reference(66989) dwd_en_paper_related(39740) dwd_en_project(1994)
dwd_en_project_output(1994) dwd_en_report(1000)
dwd_forg_act_contro_info(1127) dwd_forg_base_info(1100) dwd_forg_beneficiary_info(6376) dwd_forg_executive_info(4911)
dwd_forg_product_info(1099) dwd_forg_shareholder_info(21197) dwd_forg_stock_fin_info(100) dwd_forg_subsidiary_info(12299)
dwd_industry_chain_info(180) dwd_industry_chain_news_info(476)
dwd_org_annual_financial_info(5452) dwd_org_bankruptcy_public_cases(2100) dwd_org_bankruptcy_public_cases_list(2100)
dwd_org_base_info(1674) dwd_org_changerecord_info(100) dwd_org_company_abnormal(2062) dwd_org_company_illegal(2100)
dwd_org_company_punish(335) dwd_org_executive_info(5600) dwd_org_financing_info(1073) dwd_org_heis_info(100)
dwd_org_important_news_info(1013) dwd_org_industry_chain_dtl(2951) dwd_org_invest_info(4298)
dwd_org_merger_acquisition_info(1022) dwd_org_opt_judicial_case(2100) dwd_org_org_product_info(1184)
dwd_org_recruit_info(2100) dwd_org_risk_shixin(2100) dwd_org_risk_tax_punish(2100) dwd_org_risk_zhixing(2100)
dwd_org_shareholder_info(2501) dwd_org_stock_base(5945) dwd_org_stock_finance_info(5553)
dwd_patent(2010) dwd_patent_abstract(2000) dwd_patent_cited(2000) dwd_patent_family(2000)
dwd_patent_legal(2000) dwd_patent_title(2010)
dwd_research_institute_base_info(100) dwd_scholar(2175) dwd_scholar_coauthor(156542)
dwd_scholar_research_direction(2155) dwd_scholar_talent_flag(2075)
dwd_special_aomen_company(100) dwd_special_hongkong_company(100) dwd_special_taiwan_company(100)
dwd_zh_author(7906) dwd_zh_journal(2081) dwd_zh_paper(2000) dwd_zh_paper_citation(2032)
dwd_zh_paper_classification(2081) dwd_zh_paper_reference(23019) dwd_zh_paper_related(39900)
dwd_zh_project(2011) dwd_zh_project_output(2011) dwd_zh_report(2000) dwd_zh_report_paper(12806)
```

> 行数是 2026-09-30 的 gkx_element 快照值，随源库更新会漂移；核对以数量级一致为准，
> 精确计数差异最终体现在 §7 的残差归因里。
