"""gkx_dwd_local 本地 DWD 库 → 新图空间 全量 e2e 驱动（部署即跑）。

复刻「前端动线」：克隆 Schema 目录 → DDL 建图结构 → 建 chain 任务 → 串行触发 → 验证。
四个阶段可独立执行，也可 --phase all 一把梭（purge+prepare+run+verify）。

用法（在 api 容器内；宿主先 docker cp 本文件进容器）：
    docker cp gkx_dwd_local_e2e.py tech-kg-api-yunfei3:/tmp/
    docker exec tech-kg-api-yunfei3 /app/.venv/bin/python /tmp/gkx_dwd_local_e2e.py --phase all
    # 单阶段（可反复执行，各阶段幂等）：
    docker exec tech-kg-api-yunfei3 /app/.venv/bin/python /tmp/gkx_dwd_local_e2e.py --phase prepare
    docker exec tech-kg-api-yunfei3 /app/.venv/bin/python /tmp/gkx_dwd_local_e2e.py --phase purge
    docker exec tech-kg-api-yunfei3 /app/.venv/bin/python /tmp/gkx_dwd_local_e2e.py --phase run
    docker exec tech-kg-api-yunfei3 /app/.venv/bin/python /tmp/gkx_dwd_local_e2e.py --phase verify

阶段说明：
    prepare  建图空间（若无，走平台 API，含向量库登记）+ 克隆源空间目录
             （definition/property/script/source 绑定改指 --datasource/--database）+ 执行 DDL
    purge    CLEAR SPACE 清全部点边（保留 TAG/EDGE/索引）+ 按 source 绑定清抽取水位
    run      按前端「新建任务」形态建 3 条 chain 任务（实体链 + 关系链A/B 交错分链
             平衡大表），串行触发并轮询终态（任务/执行在图谱构建页可见）
    verify   SUBMIT JOB STATS 后 SHOW STATS，对照锚点 + 前端视角
             （jobs/executions/审核case）收尾。实体锚点期望值自动连
             --datasource 指向的源库 COUNT（亿级源无需改脚本；COUNT 慢属
             一次性成本）；BELONGS_TO_NODE/IndustryNode 口径含回填/去重，
             自动算不出，换源须重估（--skip-manual-anchors 跳过对照）

依赖 env：MYSQL_HOST/PORT/USERNAME/PASSWORD（业务+控制库同实例）；
脚本不打印任何凭证。控制库/业务库/图空间等常量见顶部 *_DEFAULT。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import uuid

SPACE_DEFAULT = "gkx_local_1"
SOURCE_SPACE_DEFAULT = "gkx_verify_1"  # 目录模板空间（45 个 DWD 适配脚本所在）
CTRL_DB_DEFAULT = "techkg_control_yunfei3"  # 控制库：schema 目录 + 绑定 + 执行记录
BIZ_DB_DEFAULT = "techkg_global"  # 业务库：抽取水位 + 审核队列
DATASOURCE_DEFAULT = "MYSQL-DWD-LOCAL"
DATABASE_DEFAULT = "gkx_dwd_local"
CHAIN_TIMEOUT = 86400  # 单链轮询上限（秒）；亿级源默认放一天，--chain-timeout 可覆盖
TERMINAL = {"COMPLETED", "FAILED", "CANCELED", "TERMINATED", "TIMED_OUT", "CONTINUED_AS_NEW"}
WEDGE_STALL = 600  # 事件数持续不涨视为楔死（秒）


# ---------------------------------------------------------------- MySQL 直连


def mysql_conn(db: str):
    import os

    import pymysql

    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "host.docker.internal"),
        port=int(os.getenv("MYSQL_PORT", "30306")),
        user=os.getenv("MYSQL_USERNAME", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=db,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


# ---------------------------------------------------------------- prepare


def prepare(args) -> None:
    asyncio.run(_create_space(args.space, args.description))
    _clone_catalog(args)
    _run_ddl(args)


async def _create_space(space: str, description: str) -> None:
    sys.path.insert(0, "/app")
    import httpx

    import main as app_main

    transport = httpx.ASGITransport(app=app_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t", timeout=120) as c:
        r = await c.get("/api/v1/graph-spaces")
        names = [it["name"] for it in (r.json().get("data") or {}).get("items") or []]
        if space in names:
            print(f"[prepare] 图空间 {space} 已存在，跳过创建")
            return
        r = await c.post("/api/v1/graph-spaces", json={"name": space, "description": description})
        print(f"[prepare] 建空间 {space}: http={r.status_code} {r.text[:160]}")


def _clone_catalog(args) -> None:
    """克隆源空间目录到目标空间：definition/property/mapping/script/source（幂等）。"""
    conn = mysql_conn(args.ctrl_db)
    cur = conn.cursor()
    space, src = args.space, args.source_space

    # 幂等：清目标空间既有目录（子表先删，definition 后删）
    for t in ("kg_schema_source", "kg_schema_script", "kg_schema_mapping", "kg_schema_property"):
        cur.execute(
            f"DELETE t FROM {t} t JOIN kg_schema_definition d ON d.id=t.schema_id WHERE d.graph_space=%s",
            (space,),
        )
    cur.execute("DELETE FROM kg_schema_definition WHERE graph_space=%s", (space,))
    conn.commit()

    cur.execute("SELECT * FROM kg_schema_definition WHERE graph_space=%s AND is_deleted=0", (src,))
    defs = cur.fetchall()
    id_map = {d["id"]: str(uuid.uuid4()) for d in defs}
    n_prop = n_script = n_src = 0
    for d in defs:
        nid = id_map[d["id"]]
        row = dict(d)
        row["id"] = nid
        row["graph_space"] = space
        # relation 两端引用延后 UPDATE（外键 RESTRICT，首行 relation 先插会撞实体未就位）
        row["source_schema_id"] = None
        row["target_schema_id"] = None
        for k, v in (
            ("instance_count", 0),
            ("ddl_status", "pending"),
            ("ddl_error", None),
            ("ddl_executed_at", None),
        ):
            if k in row:
                row[k] = v
        _insert(cur, "kg_schema_definition", row)

        # 子表：patch=硬改字段；reset=仅当列存在时重置（各库 schema 有差异，容错）
        for table, patch, reset in (
            ("kg_schema_property", {"id": str(uuid.uuid4()), "schema_id": nid}, None),
            ("kg_schema_mapping", {"id": str(uuid.uuid4()), "schema_id": nid}, None),
            (
                "kg_schema_script",
                {"id": str(uuid.uuid4()), "schema_id": nid},
                {"last_run_status": "none", "last_run_error": None, "last_run_at": None},
            ),
            (
                "kg_schema_source",
                {
                    "id": str(uuid.uuid4()),
                    "schema_id": nid,
                    "datasource_id": args.datasource,
                    "database_name": args.database,
                },
                None,
            ),
        ):
            cur.execute(f"SELECT * FROM {table} WHERE schema_id=%s", (d["id"],))
            for sub in cur.fetchall():
                sub.update(patch)
                for k, v in (reset or {}).items():
                    if k in sub:
                        sub[k] = v
                _insert(cur, table, sub)
                if table == "kg_schema_property":
                    n_prop += 1
                elif table == "kg_schema_script":
                    n_script += 1
                elif table == "kg_schema_source":
                    n_src += 1

    for old, new in id_map.items():
        cur.execute(
            "SELECT source_schema_id, target_schema_id FROM kg_schema_definition WHERE id=%s",
            (old,),
        )
        r = cur.fetchone() or {}
        cur.execute(
            "UPDATE kg_schema_definition SET source_schema_id=%s, target_schema_id=%s WHERE id=%s",
            (id_map.get(r.get("source_schema_id")), id_map.get(r.get("target_schema_id")), new),
        )
    conn.commit()
    print(f"[prepare] 克隆目录: def={len(defs)} property={n_prop} script={n_script} source={n_src}")
    conn.close()


def _insert(cur, table: str, row: dict) -> None:
    cols = ", ".join(f"`{k}`" for k in row)
    ph = ", ".join(["%s"] * len(row))
    cur.execute(f"INSERT INTO {table} ({cols}) VALUES ({ph})", list(row.values()))


def _run_ddl(args) -> None:
    sys.path.insert(0, "/app")
    from service.schema_ddl import run_schema_ddl

    conn = mysql_conn(args.ctrl_db)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, kind, name FROM kg_schema_definition WHERE graph_space=%s AND is_deleted=0",
        (args.space,),
    )
    defs = cur.fetchall()
    ok = fail = 0
    for d in defs:
        cur.execute(
            "SELECT name, data_type, required FROM kg_schema_property WHERE schema_id=%s AND is_deleted=0 ORDER BY position",
            (d["id"],),
        )
        res = run_schema_ddl(d["kind"], d["name"], list(cur.fetchall()), graph_space=args.space)
        cur.execute(
            "UPDATE kg_schema_definition SET ddl_statement=%s, ddl_status=%s, ddl_error=%s, ddl_executed_at=%s WHERE id=%s",
            (res["statement"], res["status"], res["error"], res["executed_at"], d["id"]),
        )
        if res["status"] == "succeeded":
            ok += 1
        else:
            fail += 1
            print(f"[prepare] DDL FAIL {d['name']}: {res['error']}")
    conn.commit()
    print(f"[prepare] DDL: 成功 {ok} / 失败 {fail} / 总 {len(defs)}")
    conn.close()


# ---------------------------------------------------------------- purge


def purge(args) -> None:
    sys.path.insert(0, "/app")
    from infra.graph_db import get_space_client

    c = get_space_client(args.space)
    try:
        c.execute_write(f"CLEAR SPACE {args.space}")
        print(f"[purge] CLEAR SPACE {args.space} 已提交")
    except Exception as ex:  # noqa: BLE001
        raise SystemExit(f"[purge] CLEAR SPACE 失败: {ex}") from ex

    # 水位键 = (workflow definition id, 'source:' + 绑定 uuid)——按目标空间绑定精确清
    conn = mysql_conn(args.ctrl_db)
    cur = conn.cursor()
    cur.execute(
        """SELECT s.id FROM kg_schema_source s JOIN kg_schema_definition d ON d.id=s.schema_id
           WHERE d.graph_space=%s""",
        (args.space,),
    )
    sids = [r["id"] for r in cur.fetchall()]
    conn.close()
    if not sids:
        print("[purge] 无绑定，跳过水位清理")
        return
    biz = mysql_conn(args.biz_db)
    bcur = biz.cursor()
    ph = ",".join(["%s"] * len(sids))
    bcur.execute(
        f"DELETE FROM kg_script_watermark WHERE step_id IN ({ph})", [f"source:{s}" for s in sids]
    )
    biz.commit()
    print(f"[purge] 清水位 {bcur.rowcount} 行（绑定 {len(sids)} 个）")
    biz.close()


# ---------------------------------------------------------------- run


def _load_runnable(ctrl_db: str, space: str):
    """有脚本且有绑定（chain 入链前置）的 schema：实体序 + 关系交错分两链。"""
    conn = mysql_conn(ctrl_db)
    cur = conn.cursor()
    cur.execute(
        """SELECT d.id, d.kind FROM kg_schema_definition d
           WHERE d.graph_space=%s AND d.is_deleted=0
             AND EXISTS (SELECT 1 FROM kg_schema_script sc WHERE sc.schema_id=d.id)
             AND EXISTS (SELECT 1 FROM kg_schema_source so WHERE so.schema_id=d.id)
           ORDER BY d.name""",
        (space,),
    )
    rows = cur.fetchall()
    conn.close()
    ents = [r["id"] for r in rows if r["kind"] == "entity"]
    rels = [r["id"] for r in rows if r["kind"] == "relation"]
    # 偶/奇位交错分链，把 CITES/COAUTHOR_WITH 等大表天然分开，两链时长均衡
    chain_a = [sid for i, sid in enumerate(rels) if i % 2 == 0]
    chain_b = [sid for i, sid in enumerate(rels) if i % 2 == 1]
    return ents, chain_a, chain_b


def run(args) -> None:
    asyncio.run(_run_chains(args))


async def _run_chains(args) -> None:
    sys.path.insert(0, "/app")
    import httpx

    import main as app_main

    ents, a, b = _load_runnable(args.ctrl_db, args.space)
    print(f"[run] 可跑 schema: 实体 {len(ents)} | 关系A {len(a)} | 关系B {len(b)}")
    transport = httpx.ASGITransport(app=app_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t", timeout=120) as c:
        # 幂等：同名旧任务先删
        r = await c.get("/api/v1/workflow-system/jobs", headers={"X-Graph-Space": args.space})
        for it in (r.json().get("data") or {}).get("items") or []:
            if str(it.get("name") or "").startswith("gkx本地e2e-"):
                await c.delete(f"/api/v1/workflow-system/jobs/{it['id']}")
                print(f"[run] 删除旧任务 {it['name']} ({it['id']})")

        job_ids = []
        for name, schema_ids in (
            ("gkx本地e2e-实体链", ents),
            ("gkx本地e2e-关系链A", a),
            ("gkx本地e2e-关系链B", b),
        ):
            if len(schema_ids) < 2:
                print(f"[run] {name} 仅 {len(schema_ids)} 个 schema（chain 需 ≥2），跳过")
                job_ids.append(None)
                continue
            r = await c.post(
                "/api/v1/workflow-system/jobs",
                json={
                    "name": name,
                    "taskType": "chain",
                    "schemaIds": schema_ids,
                    "graphSpace": args.space,
                    "schedule": {"kind": "once"},
                    "runNow": False,
                },
            )
            d = r.json().get("data") or {}
            jid = d.get("id") or (d.get("job") or {}).get("id")
            print(
                f"[run] 建任务 {name}: http={r.status_code} id={jid}"
                + ("" if jid else f" {r.text[:160]}")
            )
            job_ids.append(jid)

        # 串行：实体先入图，关系链随后（chain 内部已按 schemaIds 顺序串行）。
        # 轮询走 Temporal describe 而非平台 API：平台把 describe 瞬时 NotFound 一律
        # 误写成 TERMINATED 终态（不可逆），Temporal 直查免疫；楔死（worker 并发 1，
        # 大历史回放被饿死在 10s workflow-task 时限外）则 cancel 后重触发水位续跑。
        from service.temporal_runtime import temporal_runtime

        tclient = await temporal_runtime.client()
        for name, jid in zip(("实体链", "关系链A", "关系链B"), job_ids, strict=True):
            if not jid:
                continue
            status, t0 = "SKIPPED", time.time()
            for attempt in (1, 2, 3):
                t0 = time.time()
                r = await c.post(f"/api/v1/workflow-system/jobs/{jid}/trigger")
                d = r.json().get("data") or {}
                eid = d.get("id")
                wf, run = d.get("workflowId"), d.get("runId")
                print(
                    f"[run][{name}]{'[重跑]' if attempt > 1 else ''} 触发 http={r.status_code} exec={eid}"
                )
                if not wf:
                    er = await c.get(f"/api/v1/workflow-system/executions/{eid}")
                    d = er.json().get("data") or {}
                    wf, run = d.get("workflowId"), d.get("runId")
                status, n_events = await _poll_chain(tclient, wf, run, name, t0)
                if status == "COMPLETED":
                    break
                if status == "WEDGE" and attempt < 3:
                    print(f"[run][{name}] 楔死自愈：cancel 旧 run 后重触发（水位续跑）")
                    try:
                        await tclient.get_workflow_handle(wf, run_id=run).cancel()
                        await asyncio.sleep(10)
                    except Exception as ex:  # noqa: BLE001
                        print(f"[run][{name}] cancel: {ex}")
                    continue
                break
            mark = "OK" if status == "COMPLETED" else "!!"
            print(f"[run][{name}] {mark} {status} {time.time() - t0:.0f}s")


async def _poll_chain(tclient, wf: str | None, run: str | None, name: str, t0: float):
    """轮询单链：返回 (终态, 事件数)。事件数 WEDGE_STALL 不涨 → WEDGE。"""
    if not wf:
        return "NO_WF", 0
    h = tclient.get_workflow_handle(wf, run_id=run)
    last_n, last_move = -1, time.time()
    while time.time() - t0 < CHAIN_TIMEOUT:
        await asyncio.sleep(25)
        try:
            d = await h.describe()
            hist = await h.fetch_history()
            n = len(list(hist.events))
        except Exception as ex:  # noqa: BLE001
            print(f"[run][{name}] describe: {type(ex).__name__} {str(ex)[:100]}")
            await asyncio.sleep(30)
            continue
        status = d.status.name  # Py3.11 IntEnum 的 str() 是数字，必须用 .name
        if status in TERMINAL:
            return status, n
        if n != last_n:
            last_n, last_move = n, time.time()
        elif time.time() - last_move > WEDGE_STALL:
            print(f"[run][{name}] 事件数 {n} 已 {WEDGE_STALL}s 不涨，判楔死")
            return "WEDGE", n
        if int(time.time() - t0) % 300 < 25:
            print(f"[run][{name}] {status} events={n} {time.time() - t0:.0f}s")
    return "TIMEOUT", last_n


# ---------------------------------------------------------------- verify

# 实体锚点期望值 = 源库表行数，verify 时自动连源库 COUNT（换数据源/亿级规模
# 无需改脚本；亿级表 COUNT 可能要数分钟，属一次性成本）。
# 口径：Paper/Project/Report = 中英两表之和。
AUTO_ANCHORS: dict[str, list[str]] = {
    "Patent": ["SELECT COUNT(*) n FROM dwd_patent"],
    "Paper": [
        "SELECT COUNT(*) n FROM dwd_zh_paper",
        "SELECT COUNT(*) n FROM dwd_en_paper",
    ],
    "Project": [
        "SELECT COUNT(*) n FROM dwd_zh_project",
        "SELECT COUNT(*) n FROM dwd_en_project",
    ],
    "Report": [
        "SELECT COUNT(*) n FROM dwd_zh_report",
        "SELECT COUNT(*) n FROM dwd_en_report",
    ],
}

# 关系/派生锚点：口径含回填与去重，源表直 COUNT 不等值，换源须人工重估
# （估不出就置 None，verify 只打印图内值不判差）。当前值 = gkx_local_1 本机口径。
MANUAL_ANCHORS: dict[str, int | None] = {
    "BELONGS_TO_NODE": 2943,  # 链上企业×节点去重（org_base_info 回填后）
    "IndustryNode": 180,  # dwd_industry_chain_info 182 − 2 链行
}


def _source_conn(args):
    """按 --datasource 从业务库解析源库连接（凭证不打印；缺登记返回 None）。"""
    import pymysql

    biz = mysql_conn(args.biz_db)
    cur = biz.cursor()
    cur.execute(
        "SELECT host, port, username, password FROM platform_mysql_datasource WHERE id=%s",
        (args.datasource,),
    )
    row = cur.fetchone()
    biz.close()
    if not row:
        return None
    return pymysql.connect(
        host=row["host"],
        port=int(row["port"]),
        user=row["username"],
        password=row["password"],
        database=args.database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def _anchor_expectations(args) -> dict[str, int | None]:
    """AUTO 锚点向源库 COUNT（连接失败降级为 None=只打印不判差）。"""
    expects: dict[str, int | None] = {}
    try:
        src = _source_conn(args)
    except Exception as exc:  # noqa: BLE001
        print(f"[verify] 源库连接失败（数据源 {args.datasource}），自动锚点降级: {exc}")
        src = None
    if src is not None:
        cur = src.cursor()
        for tag, sqls in AUTO_ANCHORS.items():
            total = 0
            t0 = time.time()
            try:
                for sql in sqls:
                    cur.execute(sql)
                    total += int((cur.fetchone() or {}).get("n", 0))
                expects[tag] = total
                print(f"[verify] 源库锚点 {tag:20} = {total:>12,}（COUNT {time.time() - t0:.1f}s）")
            except Exception as exc:  # noqa: BLE001  # 换源表名缺失等：降级
                print(f"[verify] 锚点 {tag} COUNT 失败，降级只打印: {exc}")
                expects[tag] = None
        src.close()
    else:
        print(f"[verify] 业务库未登记数据源 {args.datasource}，自动锚点降级只打印")
        for tag in AUTO_ANCHORS:
            expects[tag] = None
    for tag, val in MANUAL_ANCHORS.items():
        expects[tag] = None if args.skip_manual_anchors else val
    return expects


def verify(args) -> None:
    sys.path.insert(0, "/app")
    from infra.graph_db import get_space_client

    c = get_space_client(args.space)
    c.execute_query("SUBMIT JOB STATS")
    time.sleep(15)
    rows = c.execute_query("SHOW STATS").records
    stats = {r["Name"]: int(r["Count"]) for r in rows if r.get("Type") in ("Tag", "Edge")}
    tags = {r["Name"] for r in c.execute_query("SHOW TAGS").records}
    n_vertex = sum(v for k, v in stats.items() if k in tags)
    n_edge = len(stats) and sum(v for k, v in stats.items() if k not in tags)
    print(f"[verify] 图内: 点 {n_vertex} / 边 {n_edge}（{len(stats)} 项 TAG/EDGE）")
    expects = _anchor_expectations(args)
    print("[verify] 锚点对照：")
    all_ok = True
    judged = 0
    for k, expect in expects.items():
        got = stats.get(k)
        if expect is None:
            print(f"    {k:20} 期望 {'?':>12} 实际 {str(got):>12} （无期望值，仅展示）")
            continue
        judged += 1
        ok = got == expect
        all_ok = all_ok and ok
        print(f"    {k:20} 期望 {expect:>12,} 实际 {str(got):>12} {'OK' if ok else '<-- 差'}")
    asyncio.run(_verify_frontend_view(args))
    if judged == 0:
        print("[verify] 结论: 无可判定锚点（自动/手工期望全缺）")
    else:
        print(f"[verify] 结论: 锚点{'全部吻合' if all_ok else '存在偏差'}（{judged} 项判定）")


async def _verify_frontend_view(args) -> None:
    sys.path.insert(0, "/app")
    import httpx

    import main as app_main

    transport = httpx.ASGITransport(app=app_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t", timeout=60) as c:
        h = {"X-Graph-Space": args.space}
        r = await c.get("/api/v1/workflow-system/jobs", headers=h)
        jobs = r.json().get("data") or {}
        print(f"[verify] 前端·图谱构建任务: total={jobs.get('total')}")
        for it in jobs.get("items") or []:
            print("    ", {k: it.get(k) for k in ("id", "name", "status", "lastExecutionStatus")})
        r = await c.get("/api/v1/workflow-system/executions", params={"limit": 3}, headers=h)
        d = r.json().get("data") or {}
        print(f"[verify] 前端·执行历史: total={d.get('total')}")
        for it in (d.get("items") or [])[:3]:
            print("    ", {k: it.get(k) for k in ("id", "definitionId", "status")})

    biz = mysql_conn(args.biz_db)
    cur = biz.cursor()
    cur.execute(
        "SELECT COUNT(*) n FROM manual_review_case WHERE created_at > NOW() - INTERVAL 1 DAY"
    )
    n = (cur.fetchone() or {}).get("n", 0)
    print(f"[verify] 人工审核: 近 24h 新建 case {n} 条（全成功抽取应为 0——零失败即无审核来源）")
    biz.close()


# ---------------------------------------------------------------- main


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--phase", choices=["prepare", "purge", "run", "verify", "all"], required=True)
    p.add_argument("--space", default=SPACE_DEFAULT, help="目标图空间")
    p.add_argument("--source-space", default=SOURCE_SPACE_DEFAULT, help="目录模板空间")
    p.add_argument("--ctrl-db", default=CTRL_DB_DEFAULT, help="控制库（schema 目录）")
    p.add_argument("--biz-db", default=BIZ_DB_DEFAULT, help="业务库（水位/审核）")
    p.add_argument("--datasource", default=DATASOURCE_DEFAULT, help="绑定指向的数据源 id")
    p.add_argument("--database", default=DATABASE_DEFAULT, help="绑定指向的库名")
    p.add_argument("--description", default="gkx_dwd_local 本地 DWD 库全量 e2e")
    p.add_argument(
        "--chain-timeout",
        type=int,
        default=CHAIN_TIMEOUT,
        help="单链轮询上限秒数（亿级源按数据量调）",
    )
    p.add_argument(
        "--skip-manual-anchors",
        action="store_true",
        help="跳过手工锚点对照（换源后口径未重估时用）",
    )
    args = p.parse_args()
    globals()["CHAIN_TIMEOUT"] = args.chain_timeout  # _poll_chain 读模块常量

    if args.phase in ("all", "purge"):
        purge(args)
    if args.phase in ("all", "prepare"):
        prepare(args)
    if args.phase in ("all", "run"):
        run(args)
    if args.phase in ("all", "verify"):
        verify(args)


if __name__ == "__main__":
    main()
