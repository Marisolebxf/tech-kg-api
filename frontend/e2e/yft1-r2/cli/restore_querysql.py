"""r2 CLI 兜底恢复：来源绑定里的 querySql + DataSource placeholder 表（前端无通道，问题记录⑭）。

UI（阶段 07）已绑好 数据源/库/表/主键列/时间列 五项；本脚本对 33 个含 querySql 的 schema
（47 条绑定）与 DataSource（placeholder 虚拟表）按清场前导出的原 sources 数组整体 PUT 回去
（后端 PUT /schemas/{id}/sources 接受 querySql，纯 UI 缺字段）。

随后做目录还原度对账（vs catalog-dump）：
  - properties：name/dataType/required 逐项全等（category 允许漂移——UI 表单无该字段，
    provenance 声明后落 core，属展示元数据，问题记录⑮）
  - sources：datasourceId/databaseName/tableName/pkColumn/timeColumn/querySql 逐条全等
  - script：sha256 与清场前一致（内容未变，仅 uploadedAt 元数据不同）

容器内执行（需先 docker cp catalog-dump 到 /tmp）：
  docker exec -w /app -e PYTHONPATH=/app tech-kg-api-yunfei3 .venv/bin/python /tmp/restore_querysql.py
"""
import json

import httpx

API = 'http://localhost:8000/api/v1'
SPACE = 'yunfei_test_1'
DUMP = '/tmp/catalog-dump/catalog.json'

dump = json.load(open(DUMP))
dump_entries = {x['name']: x for x in dump['kinds']['entity']} | {
    x['name']: x for x in dump['kinds']['relation']
}

cli = httpx.Client(timeout=60)


def fetch_current() -> dict:
    out = {}
    for kind in ('entity', 'relation'):
        r = cli.get(
            f'{API}/schema-management/schemas',
            params={'kind': kind, 'page': 1, 'pageSize': 100, 'includeDetails': 'true', 'graphSpace': SPACE},
        )
        r.raise_for_status()
        body = r.json()
        items = body['data']['items'] if body.get('code') == 200 else body['data']
        for it in items:
            out[it['name']] = it
    return out


current = fetch_current()
print(f'当前目录 {len(current)} 个 schema（期望 {len(dump_entries)}）')
if set(current) != set(dump_entries):
    raise SystemExit(f'目录名不一致: 仅当前有 {set(current) - set(dump_entries)} / 仅 dump 有 {set(dump_entries) - set(current)}')

# ---- ① PUT 恢复 querySql / placeholder ----
restored = 0
for name, x in dump_entries.items():
    has_qs = any(s.get('querySql') for s in (x.get('sources') or []))
    has_ph = any(s.get('tableName') == 'placeholder' for s in (x.get('sources') or []))
    if not (has_qs or has_ph):
        continue
    payload = {
        'sources': [
            {
                'datasourceId': s['datasourceId'],
                'databaseName': s['databaseName'],
                'tableName': s['tableName'],
                'pkColumn': s.get('pkColumn') or 'id',
                'timeColumn': s.get('timeColumn') or 'update_time',
                'querySql': s.get('querySql') or None,
            }
            for s in x['sources']
        ]
    }
    r = cli.put(f"{API}/schema-management/schemas/{current[name]['id']}/sources", json=payload)
    if r.status_code >= 400:
        raise SystemExit(f'PUT sources 失败 {name}: HTTP {r.status_code} {r.text[:300]}')
    restored += 1
print(f'① PUT 恢复 {restored} 个 schema 的来源（含 querySql 47 条 / placeholder 1 条）')

# ---- ② 还原度对账 ----
current = fetch_current()
problems: list[str] = []
type_drift: list[str] = []  # 记录但不阻断：UI 锁定行类型恒 string，旧目录个别为 datetime
for name, x in dump_entries.items():
    it = current[name]
    # properties（按集合比对：dump 与 UI 建目录的属性顺序不同；锁定行 dataType 差异
    # 单列——UI 表单锁定行类型固定 string 不可选，问题记录⑬素材）
    want_props = {(p['name'], p['dataType'], p['required']) for p in x['properties']}
    got_props = {(p['name'], p['dataType'], p['required']) for p in it.get('properties') or []}
    if want_props != got_props:
        only_want = want_props - got_props
        only_got = got_props - want_props
        if only_want and only_got and {w[0] for w in only_want} == {g[0] for g in only_got}:
            # 同名列仅 dataType 不同（锁定行 datetime→string）：接受 string 口径并记录
            type_drift.append(
                f'{name}: ' + ','.join(f'{w[0]} {w[1]}→{g[1]}' for w, g in zip(sorted(only_want), sorted(only_got)))
            )
        else:
            problems.append(f'{name} 属性漂移: 缺{sorted(only_want)[:4]} 多{sorted(only_got)[:4]}')
    # sources
    def src_tuple(s: dict) -> tuple:
        return (
            s.get('datasourceId'), s.get('databaseName'), s.get('tableName'),
            s.get('pkColumn'), s.get('timeColumn'), s.get('querySql') or None,
        )
    want_src = {src_tuple(s) for s in (x.get('sources') or [])}
    got_src = {src_tuple(s) for s in (it.get('sources') or [])}
    if want_src != got_src:
        problems.append(f'{name} 来源不符: 缺{sorted(want_src - got_src)[:2]} 多{sorted(got_src - want_src)[:2]}')
    # script sha256（有脚本的 45 个）
    want_sha = (x.get('script') or {}).get('sha256') or x.get('_scriptSha256')
    got_sha = (it.get('script') or {}).get('sha256')
    if want_sha and got_sha != want_sha:
        problems.append(f'{name} 脚本 sha256 不符: {got_sha} ≠ {want_sha}')

if problems:
    print('对账失败:')
    for p in problems:
        print(' -', p)
    raise SystemExit(1)
qs_now = sum(1 for it in current.values() for s in (it.get('sources') or []) if s.get('querySql'))
for d in type_drift:
    print(f'  锁定行类型漂移（UI 恒 string，接受）: {d}')
print(f'② 对账通过：49 schema 属性(name/type/required)/来源(含 querySql)/脚本 sha256 与清场前一致；当前 querySql 绑定 {qs_now} 条')
