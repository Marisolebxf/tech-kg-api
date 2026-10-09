"""r2 CLI 归一化：UI 建目录产生的 NOT NULL DDL 改为全可空（问题记录⑬）。

背景：UI 建表单锁定行 required=true → build_create_ddl 生成 NOT NULL 列；平台写图路径
（write_records）感知并补缺省，但离线域（学者/机构/论文/桩对齐）用 nGQL 整行 INSERT
VERTEX/EDGE，撞 NOT NULL 整域 400——同手册 §4 的预建口径。本轮在无数据时归一化（DROP +
全可空重建），无损。

流程：
  ① 取证：SHOW CREATE 首个 TAG（含 NOT NULL）+ 探针 INSERT VERTEX 撞 400 的报错原文
  ② DROP 全部 TAG 索引 → DROP 全部 TAG/EDGE（此时空间无数据）
  ③ 按**重建后目录**（kg_schema_definition.ddl_statement）去 NOT NULL 重建 + name 索引 + REBUILD
  ④ 复核：SHOW CREATE 无 NOT NULL、SHOW TAGS/EDGES 数量与目录一致

容器内执行：
  docker exec -w /app -e PYTHONPATH=/app tech-kg-api-yunfei3 .venv/bin/python /tmp/normalize_ddl.py
"""
import re
import time

from infra.graph_db import get_space_client
from infra.workflow_mysql import workflow_session_scope
from db_model.schema_management import GraphSchemaDefinition
from sqlalchemy import select

SPACE = 'yunfei_test_1'

base = get_space_client(SPACE)


def q(stmt: str) -> list[dict]:
    return [r for r in base.execute_query(stmt).records if isinstance(r, dict)]


def w(stmt: str) -> None:
    """带退避重试的写（DDL 传播延迟后紧跟的语句会瞬时 500，手册 §4 口径）。"""
    for i in range(5):
        try:
            base.execute_write(stmt)
            return
        except Exception as e:  # noqa: BLE001
            if i == 4:
                raise
            print(f'  重试: {str(e)[:100]}')
            time.sleep(1 + i)


# ---- ① 取证：NOT NULL DDL + 探针整行写入 400 ----
# 目录活表在控制库 techkg_control（infra.mysql 默认连业务库只见残留表，问题记录⑨）
with workflow_session_scope() as s:
    defs = (
        s.execute(
            select(
                GraphSchemaDefinition.name,
                GraphSchemaDefinition.kind,
                GraphSchemaDefinition.ddl_statement,
            )
            .where(GraphSchemaDefinition.graph_space == SPACE)
            .where(GraphSchemaDefinition.is_deleted == False)  # noqa: E712
        )
        .all()
    )
tags = sorted(d.name for d in defs if d.kind == 'entity')
edges = sorted(d.name for d in defs if d.kind == 'relation')
ddl_by_name = {d.name: d.ddl_statement for d in defs}
print(f'目录：{len(tags)} TAG / {len(edges)} EDGE')

first = tags[0]
show = q(f'SHOW CREATE TAG `{first}`')[0]
create_stmt = next(v for v in show.values() if isinstance(v, str) and v.strip().startswith('CREATE'))
notnull_cols = re.findall(r'(\w+)\s+\w+\s+NOT NULL', create_stmt)
print(f'① SHOW CREATE {first} 含 NOT NULL 列 {len(notnull_cols)} 个: {notnull_cols[:8]}...')
probe = f'INSERT VERTEX `{first}`(id) VALUES "r2-probe-notnull":("probe")'
try:
    base.execute_write(probe)
    print('① 探针 INSERT 竟然成功（不应发生），删除探针点后中止')
    w('DELETE VERTEX "r2-probe-notnull" WITH EDGE')
    raise SystemExit('探针成功 = DDL 无 NOT NULL，无需归一化？请人工确认')
except SystemExit:
    raise
except Exception as e:  # noqa: BLE001
    print(f'① 探针整行写入被拒（预期）: {str(e)[:200]}')

# ---- ② 清掉现有索引与类型 ----
for idx in [r.get('Index Name') or r.get('Name') for r in q('SHOW TAG INDEXES')]:
    if idx:
        w(f'DROP TAG INDEX IF EXISTS `{idx}`')
        print(f'② DROP TAG INDEX {idx}')
for kw, names in (('TAG', tags), ('EDGE', edges)):
    for n in names:
        w(f'DROP {kw} IF EXISTS `{n}`')
print(f'② DROP {len(tags)} TAG / {len(edges)} EDGE 完成')

# ---- ③ 按重建后目录全可空重建 ----
for d in sorted(defs, key=lambda x: (x.kind != 'entity', x.name)):
    stmts = [s.strip() for s in (d.ddl_statement or '').split(';') if s.strip()]
    create = next(s for s in stmts if s.upper().startswith('CREATE'))
    create = re.sub(r'\s+NOT NULL', '', create, flags=re.IGNORECASE)
    create = re.sub(r'^CREATE\s+(TAG|EDGE)\s+(IF NOT EXISTS\s+)?', r'CREATE \1 IF NOT EXISTS ', create)
    w(create.rstrip())
    if d.kind == 'entity':
        idx = f'idx_{d.name.lower()}_name'
        w(f'CREATE TAG INDEX IF NOT EXISTS `{idx}` ON `{d.name}`(name(64))')
        for i in range(5):
            try:
                base.execute_query(f'REBUILD TAG INDEX `{idx}`')
                break
            except Exception:  # noqa: BLE001
                time.sleep(2)
    print(f'③ 重建 {d.kind} {d.name}')

# ---- ④ 复核 ----
time.sleep(2)
show = q(f'SHOW CREATE TAG `{first}`')[0]
create_stmt = next(v for v in show.values() if isinstance(v, str) and v.strip().startswith('CREATE'))
if re.search(r'NOT NULL', create_stmt, flags=re.IGNORECASE):
    raise SystemExit(f'复核失败: {first} 仍含 NOT NULL')
got_tags = [r.get('Name') for r in q('SHOW TAGS')]
got_edges = [r.get('Name') for r in q('SHOW EDGES')]
print(f'④ 复核通过：{first} 已全可空；SHOW TAGS {len(got_tags)} / SHOW EDGES {len(got_edges)}')
if set(got_tags) != set(tags) or set(got_edges) != set(edges):
    raise SystemExit(f'类型集合不一致: tags 差 {set(got_tags) ^ set(tags)} / edges 差 {set(got_edges) ^ set(edges)}')
print('归一化完成')
