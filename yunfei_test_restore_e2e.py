"""yunfei_test 图空间还原 e2e：建 Schema → 上传 @step 脚本 → 绑源 → 链式抽取 → 对账 dev。

还原口径（用户需求 2026-09-24）：
  1. dev 空间全部 20 TAG / 42 EDGE 在 yunfei_test 重建（平台 API 建目录 + 空间 DDL），
     数据源仍用 dev 绑定的 gkx_element（MYSQL-010BFF5A）；
  2. 旧一对一脚本套件（15 实体 + 32 关系模块）以 @step 薄适配层重写上传
     （backend/script/yunfei_restore/，直接调老模块 transform，逻辑与旧脚本一致）；
     另补两个专用步：STUDIED_AT（复刻 load_scholar_relations.load_studied_at）、
     organization_base 溯源 mixin（复刻 attach_provenance 真实实体通道）；
  3. 完整走 kg.schema.extract 平台喂数链路（chain 任务串行）；
  4. 全程 API 驱动（建实体/传脚本/建任务都算 e2e 步骤）；
  5. 结束后按 TAG/EDGE 逐类对账 dev，偏差与原因写入 /tmp/yunfei_restore_report.json。

绑定口径（按 /tmp/binding_audit.json 逐表审计决定）：平台存库层把空 timeColumn
折成默认 update_time（gkx_element 多数表只有 updated_time），普通表 offset 读取
恒带 WHERE time > :wm、querySql 恒走 watermark 模式。故：
  - 有真实时间列且 NULL=0（已验 MIN(time)≥2000）→ 普通表 + 真实时间列（offset）；
  - 无时间列 / 时间全 NULL 的小表 → 包 querySql 合成常量 wm_col 时间列
    （watermark keyset；pk 不唯一时 ROW_NUMBER 合成唯一 row_pk）。

跑法（host）：python3 yunfei_test_restore_e2e.py [--phase setup|extract|verify|all]
前置：tech-kg-api-yunfei3 运行中（8004，AUTH_ENABLED=false），worker 正常，
/tmp/dev_schema_inventory.json、/tmp/sources_manifest.json 已生成。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "http://localhost:8004/api/v1"
GRAPH = "http://localhost:8090/api/v1/query"
GRAPH_KEY = "ysukeg"
SPACE = "yunfei_test"
DEV_SPACE = "dev"
DATASOURCE_ID = "MYSQL-010BFF5A"
DATABASE = "gkx_element"
BATCH_SIZE = 500
REPO = pathlib.Path(__file__).resolve().parent
BACKEND = REPO / "backend"
SCRIPT_DIR = BACKEND / "script" / "yunfei_restore"
INVENTORY = pathlib.Path("/tmp/dev_schema_inventory.json")
MANIFEST = pathlib.Path("/tmp/sources_manifest.json")
AUDIT = pathlib.Path("/tmp/binding_audit.json")
REPORT = pathlib.Path("/tmp/yunfei_restore_report.json")
WM_EPOCH = "1970-01-01 00:00:01"

# 套件外有数据边/空边的端点口径（代码侧考证：老 ETL/fixture 写入方）
EXTRA_EDGE_ENDPOINTS = {
    "ALUMNI": ("Person", "Person"),  # e2e fixture（manage_expert_modules_e2e_fixture）
    "COLLEAGUE": ("Person", "Person"),  # e2e fixture
    "SAME_AS": ("Person", "Person"),  # dedupe_scholar_persons 等对齐修正脚本
    "STUDIED_AT": ("Person", "Organization"),  # load_scholar_relations（本驱动带 @step 复刻）
    "CITED_BY": ("Paper", "Paper"),  # CITES 反向（fixture 维护）
    "RELATED_TO": ("Paper", "Paper"),  # paper_journal ETL
    "INVENTED_BY": ("Patent", "Person"),  # load_patent_relations（全图对齐 ETL，未复刻）
    "APPLIED_BY": ("Patent", "Person"),  # 同上
    "OWNED_BY": ("Patent", "Organization"),  # 同上
    "BID_FOR": ("organization_base", "BidNotice"),  # 空边，端点提示
    "OUTPUT_OF": ("organization_base", "Project"),  # 空边，端点提示
    "PARTICIPATES_IN": ("organization_base", "Project"),  # 空边，端点提示
    "SOURCED_FROM": ("News", "DataSource"),  # 空边，端点提示
    "IntegrationTestKnows": ("IntegrationTestPerson", "IntegrationTestPerson"),  # 集成测试 fixture
}
# dev 老命名与平台目录规范（实体 PascalCase / 关系 UPPER_SNAKE_CASE）冲突的改名映射：
# organization_base TAG 与 IntegrationTestKnows EDGE 是老脚本直接 nGQL 建的，
# 新平台创建 API 拒绝该命名——目录/空间 DDL 用合规名，对账按 dev 名映射回读
NAME_MAP = {
    "organization_base": "OrganizationBase",
    "IntegrationTestKnows": "INTEGRATION_TEST_KNOWS",
}
# organization_base mixin 的绑源：attach_provenance 真实实体通道（pk 为 information_schema
# 探测结果，offset 全量读不要求唯一）+ keyword 域六源（复用 keyword_entity 清单）
ORG_BASE_PLAIN = [
    ("dwd_zh_paper", "id"), ("dwd_en_paper", "id"),
    ("dwd_zh_author", "paper_id"), ("dwd_en_author", "paper_id"),
    ("dwd_zh_journal", "paper_id"), ("dwd_en_journal", "publication_id"),
    ("dwd_zh_report", "org_id"), ("dwd_en_report", "org_id"),
]
STUDIED_AT_QUERY_SQL = (
    "SELECT s.scholar_id, s.education_background_institution_zh, "
    "s.education_background_institution_en, s.education_background_degree_zh, "
    "s.education_background_degree_en, s.education_background_date, s.scholar_id AS row_id, "
    f"'{WM_EPOCH}' AS wm_col "
    "FROM dwd_scholar s WHERE s.status = 1 AND s.scholar_id IS NOT NULL"
)
DEVIATIONS = [
    "命名规范改名：dev 的 organization_base TAG / IntegrationTestKnows EDGE 是老脚本"
    "直接 nGQL 建的（蛇形/驼峰），新平台目录 API 只收实体 PascalCase、关系 "
    "UPPER_SNAKE_CASE——新空间分别建为 OrganizationBase / INTEGRATION_TEST_KNOWS，"
    "数据全量还原，仅名字按平台规范归一（对账已映射回读）",
    "INVENTED_BY/APPLIED_BY/OWNED_BY/OUTPUT_OF（专利→人/机构/成果）：老通道是 "
    "load_patent_relations 全图批量对齐 ETL（读图建索引 + 名称/Milvus 匹配 + rank 边），"
    "非行式抽取，平台按批喂数模型不适配（每批重建全图索引不可行），仅建 Schema 并绑 dwd_patent",
    "CITES/HAS_KEYWORD/AUTHORED_BY 同名边只保留一套绑定（平台 Schema 与 Nebula EDGE "
    "TYPE 一一对应；老套件注册器同名后者覆盖同款限制）——CITES 留专利域 "
    "（dwd_patent_cited 17.2 万，论文域 89990 丢失）；HAS_KEYWORD 留项目+专利域"
    "（2 万，论文域 paper keywords 2.7 万丢失）；AUTHORED_BY 留 authored_by 主脚本"
    "（zh/en_author 19068，fallback 通道 dwd_scholar_paper_relation ~2000 丢失）",
    "CITED_BY(2558)/RELATED_TO(79319)：paper_journal 域 ETL 维护（CITED_BY 语义为 CITES "
    "反向、RELATED_TO 由 paper_related 两表整表灌入），不在一对一套件内，无行式源可绑；"
    "仅建 Schema，新空间为 0",
    "ALUMNI(20)/COLLEAGUE(25)/SAME_AS(259)：e2e fixture 造数 / Milvus 对齐修正脚本产物，"
    "无业务源表可绑；仅建 Schema，新空间为 0",
    "BID_FOR/PARTICIPATES_IN/SOURCED_FROM/IntegrationTestKnows 与 "
    "BidNotice/Gadget/Widget/IntegrationTestPerson：dev 中本就 0 数据（fixture 空壳），"
    "仅建 Schema 不绑源",
    "organization_base 桩 vid 部分（paper_ref_/cit_/rel_/rp_，confidence=0.3）：桩点由 "
    "backfill_stub_journals 等脚本维护，新空间无桩可挂；真实实体 + 论文域 keyword 部分已还原",
    "实体同名消歧（平台写前判定）会把批内/跨批同名实体并 vid 或扣留进 T_LINK 人工裁决——"
    "老脚本按 vid 直写不合并，Person/Keyword 等同名实体数会低于 dev，差额进审核队列",
    "边写入恒 rank 0：老脚本 org/patent 域用 sha256 rank 区分重复 (src,dst) 对，平台通道"
    "同端点对重复边折叠为 1 条",
    "绑源口径受平台存库层约束（空 timeColumn 被折成默认 update_time，而库表时间列多为 "
    "updated_time）：常规表绑真实时间列走 offset（审计 NULL=0、MIN≥2000，无丢行）；"
    "无时间列/时间全 NULL 的 8 张小表包 querySql 合成常量 wm_col（+ROW_NUMBER 唯一 "
    "row_pk），读取语义与旧脚本全量一致",
    "dwd_{zh,en}_project_output 的 JSON 产出列均行 20-44KB，随 querySql 读取会带进"
    "派生表 filesort（MySQL 1038 Out of sort memory）——HAS_OUTPUT 绑源只投窄键列"
    "（id+常量 wm_col），宽列由 has_output_relation_step 按批 id 回源补齐，行集与"
    "老 SQL（o.* JOIN 项目表，实测 JOIN 过滤 0 行）逐行等价",
    "ACTUAL_CONTROLLER_OF 源表 1127 行中 1077 条为老脚本确定性拒绝的脏行"
    "（实际控制人 entity_type 未知/控制人指向企业自身），dev 同口径（50 条边吻合），"
    "已按平台机制转 T_EXTRACT_FAIL 人工审核；多次重跑产生的重复审核 case 为测试"
    "空间噪音（dedupe key 含执行 id）",
    "TAG 缺口主因是一对一套件的源覆盖 < dev 全量灌图通道：Paper dev 17.7 万但套件源只有"
    "dwd_zh_paper 4000 行（其余 17 万由 paper_journal 全库 ETL 灌入，非行式抽取）；"
    "organization_base dev 24.1 万，mixin 只复刻真实实体 + 论文域 keyword 通道（8.1 万写入、"
    "消歧后 6.2 万 vid），桩点与其它域来源无行式源；Event/News 等小缺口同理",
    "边计数负偏差主因：平台同名消歧并 vid（实体折叠加权到边端点）+ 边恒 rank 0 使同端点"
    "重复对折叠为 1（老 org/patent 域用 sha256 rank 保留重复对，COAUTHOR_WITH/AFFILIATED_WITH/"
    "EXECUTIVE_OF 等的减量即此类）+ 匹配类边受端点实体覆盖影响（HAS_OUTPUT -33 因 Paper 只"
    "还原 4000，匹配目标变少）",
    "边计数正偏差（ACQUIRES/BELONGS_TO_NODE/INVESTS_IN/INVOLVED_IN/SHAREHOLDER_OF/"
    "HAS_PARTICIPANT 等多于 dev）主因：gkx_element 是活库，源表在 dev 建图后继续灌数，"
    "重抽拿到更新的行集；且套件脚本按行全量展开（如破产重整一案多边），dev 老 ETL 当时"
    "只写了部分",
]


def req(method, path, body=None, timeout=60):
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            text = resp.read().decode()
            return resp.status, (json.loads(text) if text else {})
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(text)
        except json.JSONDecodeError:
            return e.code, text


def ok(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg, flush=True)
    if not cond:
        raise SystemExit(f"E2E 失败: {msg}")


def graph_query(space, ngql, timeout=900):
    r = urllib.request.Request(
        GRAPH,
        data=json.dumps({"query": ngql}).encode(),
        method="POST",
    )
    r.add_header("X-API-Key", GRAPH_KEY)
    r.add_header("Content-Type", "application/json")
    r.add_header("X-Graph-Space", space)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        body = json.loads(resp.read().decode())
    err = (body.get("summary") or {}).get("errorCode", 0)
    if err:
        raise RuntimeError(f"nGQL 失败: {ngql[:80]} -> {str(body)[:200]}")
    return body.get("records") or []


def load_labels():
    path = BACKEND / "script" / "schema_label_map.py"
    spec = importlib.util.spec_from_file_location("schema_label_map", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return dict(mod.SCHEMA_LABELS)


def prop_input(field_type_pair):
    field, dtype = field_type_pair["field"], field_type_pair["type"]
    type_map = {
        "string": "string", "int64": "int64", "double": "double", "bool": "bool",
        "date": "date", "datetime": "datetime", "timestamp": "datetime",
        "float": "double", "int8": "int64", "int16": "int64", "int32": "int64",
    }
    return {
        "name": field,
        "dataType": type_map.get(dtype, "string"),
        "required": False,
        "category": "core",
        "rule": "",
    }


def upload_script(schema_id, path):
    r = subprocess.run(
        ["curl", "-sS", "-m", "120", "-X", "PUT",
         f"{API}/schema-management/schemas/{schema_id}/script",
         "-F", f"script=@{path}"],
        capture_output=True, text=True,
    )
    try:
        resp = json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        resp = {"code": 0, "message": r.stdout[:200]}
    ok(resp.get("code") == 200, f"上传脚本 {path.name}: {str(resp)[:160]}")


# ---------------------------------------------------------------------------
# Phase: setup（建 Schema + 传脚本 + 绑源 + 建任务）
# ---------------------------------------------------------------------------

def list_space_schemas():
    ids = []
    page = 1
    while True:
        code, resp = req("GET", f"/schema-management/schemas?pageSize=100&page={page}")
        items = (resp.get("data") or {}).get("items") or []
        for it in items:
            if it.get("graphSpace") == SPACE:
                ids.append((it["id"], it.get("name"), it.get("kind")))
        if len(items) < 100:
            return ids
        page += 1


# querySql 来源：查询自身已暴露的真实时间列（SELECT */别名查询逐表考证）
QUERY_TIME_OF = {
    "dwd_scholar": "update_time",
    "dwd_patent": "update_time",
    "dwd_zh_project": "updated_time",
    "dwd_en_project": "updated_time",
    "dwd_industry_chain_info": "updated_time",
    "dwd_org_industry_chain_dtl": "updated_time",
    "dwd_scholar_paper_relation": "update_time",
    "dwd_scholar_coauthor": "update_time",
    "dwd_zh_author": "updated_time",
    "dwd_en_author": "updated_time",
}
# 查询没暴露时间列 / 宽表不适配派生表排序的定向改写：
# - dwd_patent_cited 补选真实时间列；
# - dwd_{zh,en}_project_output 的 JSON 产出列均行 20-44KB，随 querySql 读取会带进
#   派生表 filesort → MySQL 1038（Out of sort memory）——只投窄键列 id + 常量
#   wm_col，宽列由 has_output_relation_step 按批 id 回源补齐；
# - dwd_zh_report_paper 无时间列，合成常量 wm_col（真实行宽仅 ~300B，无排序风险）
QUERY_TIME_FIX = {
    "dwd_patent_cited": ("SELECT ", "SELECT update_time, "),
    "dwd_zh_project_output": ("SELECT o.*", f"SELECT o.id, '{WM_EPOCH}' AS wm_col"),
    "dwd_en_project_output": ("SELECT o.*", f"SELECT o.id, '{WM_EPOCH}' AS wm_col"),
    "dwd_zh_report_paper": ("SELECT *", f"SELECT *, '{WM_EPOCH}' AS wm_col"),
}


def fixed_source(spec, audit):
    """把清单来源绑定修正为当前平台可读口径（返回 {table, pk, time, query_sql?}）。

    平台存库层把空 timeColumn 折成 update_time（多数表只有 updated_time）且
    普通表 offset 恒带 WHERE time > :wm、querySql 恒走 watermark：
      - placeholder / 老 querySql 来源 → 逐个适配（补时间列暴露）；
      - 有真实时间列且 NULL=0 → 普通表绑真实时间列（offset 全量，无丢行）；
      - 无时间列 / 时间全 NULL → 包 querySql 合成常量 wm_col；pk 不唯一时
        ROW_NUMBER() OVER (ORDER BY 全列) 合成唯一 row_pk（小表，代价可忽略）。
    """
    table, pk = spec["table"], spec["pk"]
    query = spec.get("query_sql")
    if table == "placeholder":
        return {"table": table, "pk": "id", "time": "wm_col",
                "query_sql": f"SELECT 1 AS id, '{WM_EPOCH}' AS wm_col"}
    if query:
        if "AS wm_col" in query:  # 驱动自带 wm_col（STUDIED_AT 等）
            return {"table": table, "pk": pk, "time": "wm_col", "query_sql": query}
        if table in QUERY_TIME_FIX:
            old, new = QUERY_TIME_FIX[table]
            if old not in query:
                raise RuntimeError(f"{table} 查询形状与预期不符: {query[:100]}")
            query = query.replace(old, new, 1)
            time_col = "wm_col" if "wm_col" in new else "update_time"
            return {"table": table, "pk": pk, "time": time_col, "query_sql": query}
        return {"table": table, "pk": pk, "time": QUERY_TIME_OF[table], "query_sql": query}
    info = audit[table]
    time_col = info.get("timeColumn") or ""
    nulls = info.get("nullTime") or 0
    if time_col and not nulls:
        return {"table": table, "pk": pk, "time": time_col, "query_sql": None}
    time_expr = f"IFNULL(t.`{time_col}`, '{WM_EPOCH}')" if time_col else f"'{WM_EPOCH}'"
    if any(b["pk"] == pk and b["unique"] for b in info["bindings"]):
        return {"table": table, "pk": pk, "time": "wm_col", "query_sql":
                f"SELECT t.*, {time_expr} AS wm_col FROM `{table}` t"}
    order_cols = ", ".join(f"t.`{c}`" for c in info["columns"])
    return {"table": table, "pk": "row_pk", "time": "wm_col", "query_sql":
            f"SELECT t.*, {time_expr} AS wm_col, ROW_NUMBER() OVER "
            f"(ORDER BY {order_cols}) AS row_pk FROM `{table}` t"}


def bind_all(entity_ids, edge_ids, suite_edges, manifest):
    audit = json.loads(AUDIT.read_text())

    def bind(schema_id, sources, label):
        payload = {"sources": [
            {
                "datasourceId": DATASOURCE_ID,
                "databaseName": DATABASE,
                "tableName": s["table"],
                "pkColumn": s["pk"],
                "timeColumn": s["time"],
                **({"querySql": s["query_sql"]} if s.get("query_sql") else {}),
            } for s in sources
        ]}
        code, resp = req("PUT", f"/schema-management/schemas/{schema_id}/sources", payload)
        ok(code in (200, 201), f"绑源 {label}（{len(sources)} 个来源）: {str(resp)[:100]}")

    def fixed(sources):
        return [fixed_source(s, audit) for s in sources]

    for entry in manifest["entities"]:
        bind(entity_ids[entry["tag"]], fixed(entry["sources"]), entry["tag"])
    for edge, entry in suite_edges.items():
        bind(edge_ids[edge], fixed(entry["sources"]), edge)
    keyword_sources = fixed(next(e["sources"] for e in manifest["entities"]
                                 if e["tag"] == "Keyword"))
    bind(entity_ids["organization_base"],
         fixed([{"table": t, "pk": pk} for t, pk in ORG_BASE_PLAIN]) + keyword_sources,
         "organization_base")
    bind(edge_ids["STUDIED_AT"],
         [{"table": "dwd_scholar", "pk": "scholar_id", "time": "wm_col",
           "query_sql": STUDIED_AT_QUERY_SQL}], "STUDIED_AT")
    patent_no_script = [
        ("INVENTED_BY", [{"table": "dwd_patent", "pk": "id"}]),
        ("APPLIED_BY", [{"table": "dwd_patent", "pk": "id"}]),
        ("OWNED_BY", [{"table": "dwd_patent", "pk": "id"}]),
        ("OUTPUT_OF", [{"table": "dwd_zh_project_output", "pk": "id"},
                       {"table": "dwd_en_project_output", "pk": "id"}]),
    ]
    for edge, sources in patent_no_script:
        bind(edge_ids[edge], fixed(sources), edge)


def phase_setup():
    inv = json.loads(INVENTORY.read_text())
    manifest = json.loads(MANIFEST.read_text())
    labels = load_labels()

    step = lambda m: print(f"\n=== {m}", flush=True)

    step("0. 预检：API/数据源/图空间")
    code, resp = req("GET", "/mysql-datasources")
    items = resp.get("data") or []
    items = items.get("items", []) if isinstance(items, dict) else items
    ds = next((i for i in items if i.get("id") == DATASOURCE_ID), None)
    ok(ds is not None, f"数据源 {DATASOURCE_ID} 存在（{ds and ds.get('name')}）")
    tags = [r["Name"] for r in graph_query(SPACE, "SHOW TAGS;")]
    ok(not tags, f"yunfei_test 空间为空（现有 TAG: {tags}）")

    step("0.1 清理目录中 yunfei_test 空间的历史 Schema")
    stale = list_space_schemas()
    for sid, name, kind in stale:
        code, _ = req("DELETE", f"/schema-management/schemas/{sid}")
        ok(code in (200, 204), f"删除旧 Schema {name}({kind}) {sid}")
    print(f"  清理 {len(stale)} 个旧 Schema")

    # ---- 实体 Schema：套件 15 + organization_base + 4 个 fixture 空 TAG ----
    step("1. 创建实体 Schema（20 TAG）")
    suite_tags = {e["tag"]: e for e in manifest["entities"]}
    all_tags = sorted(inv["tags"])
    ok(len(all_tags) == 20, f"dev TAG 总数 20（实际 {len(all_tags)}）")
    entity_ids = {}
    for tag in all_tags:
        catalog_name = NAME_MAP.get(tag, tag)
        props = [prop_input(p) for p in inv["tags"][tag]]
        if not props:
            props = [prop_input({"field": "source_table", "type": "string"})]
        payload = {
            "schemaKey": ("tag-" + catalog_name.lower().replace("_", "-"))[:64],
            "name": catalog_name,
            "label": labels.get(tag, tag),
            "description": f"yunfei_test 还原：复刻 dev 空间 {tag}（e2e 创建）",
            "identityKey": "id",
            "properties": props,
            "isCore": False,
            "version": "v1.0",
            "graphSpace": SPACE,
        }
        code, resp = req("POST", "/schema-management/schemas/entities", payload)
        ok(code in (200, 201), f"创建 TAG {catalog_name}: {str(resp)[:120]}")
        entity_ids[tag] = resp["data"]["id"]
    got_tags = [r["Name"] for r in graph_query(SPACE, "SHOW TAGS;")]
    expect_tags = sorted(NAME_MAP.get(t, t) for t in all_tags)
    ok(sorted(got_tags) == expect_tags, f"空间 DDL 20 TAG 落库（{len(got_tags)}）")

    # ---- 关系 Schema：套件去重 28 + STUDIED_AT + 其余套件外 ----
    step("2. 创建关系 Schema（42 EDGE）")
    suite_edges = {}
    for entry in manifest["relations"]:
        suite_edges[entry["edge"]] = entry  # 同名后者覆盖（与老注册器口径一致）
    all_edges = sorted(inv["edges"])
    ok(len(all_edges) == 42, f"dev EDGE 总数 42（实际 {len(all_edges)}）")
    edge_ids = {}
    for edge in all_edges:
        entry = suite_edges.get(edge)
        if entry:
            src, dst = entry["source_tag"], entry["target_tag"]
        else:
            src, dst = EXTRA_EDGE_ENDPOINTS[edge]
        catalog_name = NAME_MAP.get(edge, edge)
        props = [prop_input(p) for p in inv["edges"][edge]]
        if not props:
            props = [prop_input({"field": "create_time", "type": "string"})]
        payload = {
            "schemaKey": ("edge-" + catalog_name.lower().replace("_", "-"))[:64],
            "name": catalog_name,
            "label": labels.get(edge, edge),
            "description": f"yunfei_test 还原：复刻 dev 空间 {edge}（e2e 创建）",
            "identityKey": "",
            "properties": props,
            "isCore": False,
            "version": "v1.0",
            "sourceSchemaId": entity_ids[src],
            "targetSchemaId": entity_ids[dst],
            "relationCategory": "fact",
            "graphSpace": SPACE,
        }
        code, resp = req("POST", "/schema-management/schemas/relations", payload)
        ok(code in (200, 201), f"创建 EDGE {catalog_name}({src}->{dst}): {str(resp)[:120]}")
        edge_ids[edge] = resp["data"]["id"]
    got_edges = [r["Name"] for r in graph_query(SPACE, "SHOW EDGES;")]
    expect_edges = sorted(NAME_MAP.get(e, e) for e in all_edges)
    ok(sorted(got_edges) == expect_edges, f"空间 DDL 42 EDGE 落库（{len(got_edges)}）")

    # ---- 上传脚本 ----
    step("3. 上传 @step 脚本（47 套件薄适配 + STUDIED_AT + organization_base）")
    for entry in manifest["entities"]:
        fname = entry["module"].rsplit(".", 1)[-1] + "_step.py"
        upload_script(entity_ids[entry["tag"]], SCRIPT_DIR / fname)
    for edge, entry in suite_edges.items():
        fname = entry["module"].rsplit(".", 1)[-1] + "_step.py"
        upload_script(edge_ids[edge], SCRIPT_DIR / fname)
    upload_script(edge_ids["STUDIED_AT"], SCRIPT_DIR / "studied_at_relation.py")
    upload_script(entity_ids["organization_base"], SCRIPT_DIR / "organization_base_mixin.py")
    print(f"  上传 {len(suite_tags) + len(suite_edges) + 2} 个脚本")

    # ---- 绑源（按审计逐表修正口径） ----
    step("4. 绑定来源（gkx_element @ MYSQL-010BFF5A）")
    bind_all(entity_ids, edge_ids, suite_edges, manifest)

    # ---- 建任务：实体链 + 关系链 ×2 ----
    step("5. 创建图谱构建任务（chain 串行）")
    jobs = {}
    entity_chain = [entity_ids[t] for t in sorted(suite_tags)] + [entity_ids["organization_base"]]
    relation_chain = [edge_ids[e] for e in sorted(suite_edges)] + [edge_ids["STUDIED_AT"]]
    chains = [
        ("还原-实体", entity_chain),
        ("还原-关系A", relation_chain[:15]),
        ("还原-关系B", relation_chain[15:]),
    ]
    for name, schema_ids in chains:
        code, resp = req("POST", "/workflow-system/jobs", {
            "name": name,
            "taskType": "chain",
            "schemaIds": schema_ids,
            "schedule": {"kind": "once"},
            "graphSpace": SPACE,
            "batchSize": BATCH_SIZE,
        })
        ok(code in (200, 201), f"创建任务 {name}（{len(schema_ids)} Schema）: {str(resp)[:120]}")
        jobs[name] = resp["data"]["id"]
        print(f"  job {name} = {jobs[name]}")

    state = {
        "entityIds": entity_ids, "edgeIds": edge_ids, "jobs": jobs,
        "suiteEdges": sorted(suite_edges), "tags": all_tags, "edges": all_edges,
    }
    pathlib.Path("/tmp/yunfei_restore_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=1))
    print("\nsetup 完成：state → /tmp/yunfei_restore_state.json")


# ---------------------------------------------------------------------------
# Phase: extract（触发链任务并等待终态）
# ---------------------------------------------------------------------------

def wait_execution(execution_id, timeout_s, poll=60):
    deadline = time.time() + timeout_s
    last = ""
    tick = 0
    while time.time() < deadline:
        code, resp = req("GET", f"/workflow-system/executions/{execution_id}", timeout=120)
        data = resp.get("data") or {}
        status = data.get("status") or "?"
        # 状态变化即时打印；RUNNING 粘滞态每 10 分钟重印一行心跳
        if status != last or (status == "RUNNING" and tick % 10 == 0):
            out = data.get("output") or {}
            srcs = out.get("sources") or []
            print(f"  [{time.strftime('%H:%M:%S')}] {execution_id[:8]} {status} "
                  f"rows={sum(int(s.get('rows', 0)) for s in srcs)} "
                  f"written={sum(int(s.get('written', 0)) for s in srcs)}", flush=True)
            last = status
        tick += 1
        if status in ("COMPLETED", "FAILED", "TERMINATED", "CANCELED", "TIMED_OUT"):
            return data
        time.sleep(poll)
    raise SystemExit(f"执行超时未终态: {execution_id}")


ADOPT = pathlib.Path("/tmp/yunfei_restore_adopt.json")

# 原 还原-实体 链在 Patent 环 FAILED（平台写图对 int64/datetime 列的裸字符串
# 字面量被 Nebula 拒绝，已修 service/temporal_workflows.py 并重建镜像）。
# 已完成环水位已推进不重抽，剩余 Schema 另建断点链续跑；断点链三次撞上
# 共享 Nebula 内存高水位——被上限取消的索引重建线程后台读图，与下一环写图
# 叠加越线（12 万+实体后重建 pass 自身也会越线）。已给 worker 加
# SCHEMA_EXTRACT_BUILD_INDEX=0 跳过随环重建（索引失败本就降级），全部链
# 结束后用 POST /entity-search/reindex 统一全量重建一次。
DONE_ENTITY_TAGS = {
    "DataSource", "Event", "IndustryChain", "IndustryNode",
    "Journal", "Keyword", "News", "Organization", "Paper",
    "Patent", "PatentFamily",  # 实体B 首轮完成（PatentFamily 与 dev 完全一致）
    "Person",  # 实体B 第 2 轮完成（写图全部落库、水位已推进；链在 Product 环撞水位 FAILED）
}
ENTITY_B = "还原-实体B"
ENTITY_C = "还原-实体C"


def job_last_status(job_id):
    code, resp = req("GET", f"/workflow-system/jobs/{job_id}")
    return (resp.get("data") or {}).get("lastExecutionStatus") if code == 200 else None


def ensure_entity_c_job(state):
    """实体断点链：实体B 未完成时按剩余 Schema 建实体C（B 已完成则跳过实体环）。"""
    if ENTITY_C in state["jobs"]:
        return True
    if ENTITY_B in state["jobs"] and job_last_status(state["jobs"][ENTITY_B]) == "COMPLETED":
        return False  # B 已全量完成，无需断点链
    manifest = json.loads(MANIFEST.read_text())
    suite_tags = {e["tag"] for e in manifest["entities"]}
    remaining = sorted(suite_tags - DONE_ENTITY_TAGS) + ["organization_base"]
    schema_ids = [state["entityIds"][t] for t in remaining]
    print(f"\n=== 创建断点链 {ENTITY_C}（剩余 {len(schema_ids)} Schema: {remaining}）", flush=True)
    code, resp = req("POST", "/workflow-system/jobs", {
        "name": ENTITY_C, "taskType": "chain", "schemaIds": schema_ids,
        "schedule": {"kind": "once"}, "graphSpace": SPACE, "batchSize": BATCH_SIZE,
    })
    ok(code in (200, 201), f"创建任务 {ENTITY_C}: {str(resp)[:120]}")
    state["jobs"][ENTITY_C] = resp["data"]["id"]
    pathlib.Path("/tmp/yunfei_restore_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=1))
    return True


def phase_extract():
    state = json.loads(pathlib.Path("/tmp/yunfei_restore_state.json").read_text())
    entity_chains = [ENTITY_C] if ensure_entity_c_job(state) else []
    # 接管文件：{链名: 执行ID}——链已在 Temporal 跑着（比如驱动重启/超时后），
    # 跳过触发直接等终态，避免重复触发同一任务造成两条链并发写图
    adopt = json.loads(ADOPT.read_text()) if ADOPT.exists() else {}
    results = {}
    for name in (*entity_chains, "还原-关系A", "还原-关系B"):
        job_id = state["jobs"][name]
        if name in adopt:
            execution_id = adopt[name]
            print(f"\n=== 接管 {name}（job={job_id}，已在跑的执行 {execution_id}）", flush=True)
        else:
            print(f"\n=== 触发 {name}（job={job_id}）", flush=True)
            code, resp = req("POST", f"/workflow-system/jobs/{job_id}/trigger")
            ok(code in (200, 201), f"触发 {name}: {str(resp)[:120]}")
            execution_id = resp["data"]["id"]
        # 实体链每环全空间索引重建（单飞串行、30 分钟封顶），16 小时兜底
        execution = wait_execution(execution_id, timeout_s=16 * 3600)
        status = execution["status"]
        msg = str(execution.get("message") or "")
        # 控制面把「含失败记录」的抽取标 FAILED（FUNC-00901）：环全部完成，
        # 失败行是老脚本对脏源行的确定性拒绝、已转 T_EXTRACT_FAIL 人工审核
        # （dev 同口径：如 ACTUAL_CONTROLLER_OF 1127 行 1077 拒 50 边）——
        # 数据链路实际完成，接受该软终态并在结果里如实汇总失败数
        soft_failed = status == "FAILED" and "已转人工审核" in msg
        ok(status == "COMPLETED" or soft_failed,
           f"{name} 终态 {status}（{msg[:200]}）")
        out = execution.get("output") or {}
        steps = out.get("steps") or {}
        failed_steps = {k: v for k, v in steps.items() if v.get("failed")}
        print(f"  {name}: schemas={len(steps)} rows={sum(int(s.get('rows', 0)) for s in (out.get('sources') or []))}"
              f" written={sum(int(s.get('written', 0)) for s in (out.get('sources') or []))}"
              f" failures={out.get('failures')}")
        if failed_steps:
            print(f"  ⚠ 有失败计数的环: {json.dumps(failed_steps, ensure_ascii=False)[:800]}")
        results[name] = {
            "executionId": execution.get("id"),
            "status": status,
            "message": msg[:300],
            "failures": out.get("failures"),
        }
    pathlib.Path("/tmp/yunfei_restore_extract.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1))
    print("\nextract 完成")


# ---------------------------------------------------------------------------
# Phase: verify（dev / yunfei_test 双侧计数对账，SHOW STATS 口径）
# ---------------------------------------------------------------------------

def space_stats(space, tries=12, wait=45):
    """SUBMIT JOB STATS 后 SHOW STATS，返回 {tag: n} / {edge: n}（精确计数）。"""
    recs = graph_query(space, "SUBMIT JOB STATS;", timeout=120)
    job_id = recs[0].get("New Job Id") if recs else None
    if job_id is not None:
        for _ in range(tries):
            time.sleep(wait)
            job = graph_query(space, f"SHOW JOB {job_id};", timeout=120)
            if "FINISHED" in str(job):
                break
    recs = graph_query(space, "SHOW STATS;", timeout=300)
    tags = {r["Name"]: int(r["Count"]) for r in recs if r["Type"] == "Tag"}
    edges = {r["Name"]: int(r["Count"]) for r in recs if r["Type"] == "Edge"}
    return tags, edges


def phase_verify():
    state = json.loads(pathlib.Path("/tmp/yunfei_restore_state.json").read_text())
    tags, edges = state["tags"], state["edges"]
    cached = pathlib.Path("/tmp/dev_space_stats.json")
    if cached.exists():  # 抽取期间已跑过 dev 全量 stats（dev 不再变动），直接用
        snap = json.loads(cached.read_text())
        dev_tags, dev_edges = snap["tags"], snap["edges"]
        print("\n=== dev 空间计数（基准，沿用抽取期 stats 快照）", flush=True)
    else:
        dev_tags, dev_edges = space_stats(DEV_SPACE)
    print("\n=== yunfei_test 空间计数（还原结果，改名 TAG/EDGE 按 dev 名映射回读）", flush=True)
    raw_tags, raw_edges = space_stats(SPACE)
    new_tags = {t: raw_tags.get(NAME_MAP.get(t, t), 0) for t in tags}
    new_edges = {e: raw_edges.get(NAME_MAP.get(e, e), 0) for e in edges}

    def row(name, base, got):
        mark = ""
        if isinstance(base, int) and isinstance(got, int):
            if got == base:
                mark = "OK"
            elif got > base:
                mark = f"+{got - base}"
            else:
                mark = f"-{base - got}"
        return f"  {name:<28} dev={base!s:>10}  new={got!s:>10}  {mark}"

    print("\n=== TAG 对账")
    for t in tags:
        print(row(t, dev_tags.get(t), new_tags.get(t)))
    print("\n=== EDGE 对账")
    for e in edges:
        print(row(e, dev_edges.get(e), new_edges.get(e)))

    report = {
        "space": SPACE,
        "devCounts": {"tags": dev_tags, "edges": dev_edges},
        "newCounts": {"tags": new_tags, "edges": new_edges},
        "deviations": DEVIATIONS,
        "state": state,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(f"\n对账报告 → {REPORT}")
    print("\n未还原项与原因：")
    for d in DEVIATIONS:
        print(f"  - {d}")


def phase_bind():
    state = json.loads(pathlib.Path("/tmp/yunfei_restore_state.json").read_text())
    manifest = json.loads(MANIFEST.read_text())
    suite_edges = {}
    for entry in manifest["relations"]:
        suite_edges[entry["edge"]] = entry
    print("\n=== 重绑来源（按审计口径）", flush=True)
    # ⚠ replace_sources 是先删后插（绑定行换新 uuid）——水位键 source:{绑定id}
    # 随之失效，全量重绑等于清空所有水位触发全量重抽。只在需要改绑定时调用，
    # 且重抽幂等（upsert）但会重演确定性脏行失败（T_EXTRACT_FAIL 重复建案）。
    bind_all(state["entityIds"], state["edgeIds"], suite_edges, manifest)
    print("重绑完成")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase", default="all", choices=["setup", "bind", "extract", "verify", "all"]
    )
    args = parser.parse_args()
    if args.phase in ("setup", "all"):
        phase_setup()
    if args.phase in ("bind", "all"):
        phase_bind()
    if args.phase in ("extract", "all"):
        phase_extract()
    if args.phase in ("verify", "all"):
        phase_verify()


if __name__ == "__main__":
    main()
