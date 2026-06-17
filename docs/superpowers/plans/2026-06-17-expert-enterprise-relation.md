# 专家-企业关系构建 实现计划（techkg 全流程）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** 实现"专家-企业关系构建"真实接口：建 techkg 图空间（db_model 映射 schema）、MySQL→图 ETL、API 查图、前端接线，替换前端假数据。

**Architecture:** MySQL 同步接入（SQLAlchemy+pymysql）+ dao 层；`script/` 建 techkg 图 schema 与 ETL 灌数据；`infra/graph_db` 加 techkg 空间单例；handler/application/service 实现 `POST /build` 查图组装；前端改 apiPath + fetch + 修 vite 代理。

**Tech Stack:** Python 3.13(.venv，官方 target 3.11，代码兼容)、FastAPI、SQLAlchemy 2.0、pymysql、httpx、NebulaGraph（经 trs-graph-service）、pytest、ruff（line-length 100，E/F/I/UP/B，ignore E501，exclude legacy）。

**前置（已就绪）：** `.venv` 已装 httpx/pydantic/sqlalchemy；需补装 `pymysql`（Task 1）。MySQL `techkg` 库连通、67 表全空。trs-graph 8090 可连（api_key=`ysukeg`）。

**约定：** 命令在 `backend/` 下用 `.venv/bin/python` / `.venv/bin/python -m pytest`。**commit message 一律不带协作者 trailer。** 每个 task 结束跑 `ruff check` + `ruff format`。

**TRS Graph client API（`infra.graph_db.client.TRSGraphClient`，已实现）：**
`create_node(labels:list[str], properties=None)->GraphNode`、`find_nodes(labels, properties, *, limit, offset)->GraphPagedResult`、`get_node(id)->GraphNode|None`、`get_node_edges(id, *, direction, edge_type, limit)->list[GraphEdge]`、`create_edge(source_id, target_id, edge_type, properties=None)->GraphEdge`、`execute_write(query, params=None)->GraphQueryResult`、`batch_create_nodes(items, labels)`、`node_count(label)`、`edge_count(edge_type)`、`labels()`、`edge_types()`。模型：`GraphNode(id,labels,properties)`、`GraphEdge(id,type,source_id,target_id,properties)`、`GraphPagedResult(items,total,limit,offset)`。

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `backend/infra/mysql.py`（改：实现） | 同步 SQLAlchemy engine + session + 单例 |
| `backend/dao/scholar.py`（改：实现） | ScholarDAO 查询 |
| `backend/dao/organization.py`（改：实现） | OrganizationDAO 查询 |
| `backend/infra/graph_db/__init__.py`（改） | 加 techkg 空间单例 |
| `backend/script/init_graph_schema.py`（新） | 建 techkg 空间 + Tag/Edge/Index DDL |
| `backend/script/load_graph.py`（新） | MySQL→图 ETL |
| `backend/biz/handler/expert_enterprise_relation.py`（改） | POST /build |
| `backend/application/expert_enterprise_relation.py`（改） | build 编排 |
| `backend/service/expert_enterprise_relation.py`（改） | 查图组装 |
| `backend/biz/schemas/expert_enterprise_relation.py`（新） | 请求/响应 Pydantic |
| `backend/tests/unit/test_mysql.py`（新） | mysql 单测 |
| `backend/tests/unit/test_dao_scholar.py`（新） | DAO 单测 |
| `backend/tests/unit/test_dao_organization.py`（新） | DAO 单测 |
| `backend/tests/unit/test_load_graph.py`（新） | ETL 单测 |
| `backend/tests/unit/test_expert_enterprise_service.py`（新） | service 单测 |
| `backend/tests/integration/test_expert_enterprise_api.py`（新） | API 集成（external） |
| `frontend/src/App.vue`（改） | apiPath + fetch |
| `frontend/vite.config.ts`（改） | 代理修正 |

---

## Task 1: MySQL 接入 infra/mysql.py

**Files:** Modify `backend/infra/mysql.py`; Test `backend/tests/unit/test_mysql.py`

- [ ] **Step 1: 补装 pymysql**

```bash
cd /data1/huyatao/tech-kg-api/backend
.venv/bin/python -m pip install pymysql
```

- [ ] **Step 2: 写失败测试**

创建 `backend/tests/unit/test_mysql.py`：

```python
from __future__ import annotations

from infra.mysql import MySQLClient, build_db_url


def test_build_db_url_from_env(monkeypatch):
    monkeypatch.setenv("MYSQL_HOST", "h")
    monkeypatch.setenv("MYSQL_PORT", "3307")
    monkeypatch.setenv("MYSQL_USERNAME", "u")
    monkeypatch.setenv("MYSQL_PASSWORD", "p")
    monkeypatch.setenv("MYSQL_DATABASE", "d")
    assert build_db_url() == "mysql+pymysql://u:p@h:3307/d?charset=utf8mb4"


def test_client_engine_and_session():
    client = MySQLClient(url="sqlite:///:memory:")
    assert client.engine is not None
    s = client.session()
    assert s is not None
    s.close()
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd /data1/huyatao/tech-kg-api/backend && .venv/bin/python -m pytest tests/unit/test_mysql.py -v`
Expected: FAIL — `ImportError`/`build_db_url` 不存在

- [ ] **Step 4: 实现 infra/mysql.py**

替换 `backend/infra/mysql.py`：

```python
"""MySQL 同步接入（SQLAlchemy + pymysql）。"""

from __future__ import annotations

import os
from typing import Iterator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()


def build_db_url() -> str:
    """根据 MYSQL_* 环境变量拼装 SQLAlchemy URL。"""
    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = os.getenv("MYSQL_PORT", "3306")
    user = os.getenv("MYSQL_USERNAME", "root")
    pwd = os.getenv("MYSQL_PASSWORD", "")
    db = os.getenv("MYSQL_DATABASE", "techkg")
    return f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}?charset=utf8mb4"


class MySQLClient:
    """同步 SQLAlchemy engine + session 工厂。"""

    def __init__(self, url: str | None = None) -> None:
        self._url = url or build_db_url()
        self._engine: Engine = create_engine(self._url, pool_pre_ping=True, pool_size=10)
        self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False)

    @property
    def engine(self) -> Engine:
        return self._engine

    def session(self) -> Session:
        return self._session_factory()


_client: MySQLClient | None = None


def get_mysql_client() -> MySQLClient:
    """进程级单例（懒加载，默认连 MySQL；测试可注入 sqlite）。"""
    global _client
    if _client is None:
        _client = MySQLClient()
    return _client


def get_session() -> Iterator[Session]:
    """FastAPI 依赖：yield 一个 session。"""
    client = get_mysql_client()
    session = client.session()
    try:
        yield session
    finally:
        session.close()
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd /data1/huyatao/tech-kg-api/backend && .venv/bin/python -m pytest tests/unit/test_mysql.py -v`
Expected: 2 passed

- [ ] **Step 6: ruff + 提交**

```bash
cd /data1/huyatao/tech-kg-api/backend
ruff check infra/mysql.py tests/unit/test_mysql.py && ruff format infra/mysql.py tests/unit/test_mysql.py
git add infra/mysql.py tests/unit/test_mysql.py
git commit -m "feat(mysql): implement sync SQLAlchemy MySQLClient infra"
```

---

## Task 2: DAO 层（scholar / organization）

**Files:** Modify `backend/dao/scholar.py`, `backend/dao/organization.py`; Test `backend/tests/unit/test_dao_scholar.py`, `backend/tests/unit/test_dao_organization.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/unit/test_dao_scholar.py`：

```python
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from db_model.base import Base
from db_model.scholar import DwdScholar
from dao.scholar import ScholarDAO


def _session() -> Session:
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng, tables=[DwdScholar.__table__])
    return Session(eng)


def test_get_returns_none_when_absent():
    with _session() as s:
        assert ScholarDAO(s).get("nope") is None


def test_get_and_list():
    with _session() as s:
        s.add(DwdScholar(scholar_id="S1", name_zh="张伟", scholar_org_name_zh="清华大学"))
        s.commit()
        dao = ScholarDAO(s)
        got = dao.get("S1")
        assert got is not None and got.name_zh == "张伟"
        rows = dao.list(limit=10)
        assert len(rows) == 1
```

创建 `backend/tests/unit/test_dao_organization.py`：

```python
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from db_model.base import Base
from db_model.organization import DwdOrgRegInfo
from dao.organization import OrganizationDAO


def _session() -> Session:
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng, tables=[DwdOrgRegInfo.__table__])
    return Session(eng)


def test_get_by_name_and_id():
    with _session() as s:
        s.add(DwdOrgRegInfo(org_id="O1", name_cn="清华大学", province="北京市", data_source="t"))
        s.commit()
        dao = OrganizationDAO(s)
        assert dao.get_by_id("O1").name_cn == "清华大学"
        assert dao.get_by_name("清华大学").org_id == "O1"
        assert dao.get_by_name("不存在") is None
        assert len(dao.list(limit=10)) == 1
```

注：`DwdOrgRegInfo` 有 `name_cn`/`org_id`（非空列 `name_cn`、`data_source`），插入时需给非空字段。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /data1/huyatao/tech-kg-api/backend && .venv/bin/python -m pytest tests/unit/test_dao_scholar.py tests/unit/test_dao_organization.py -v`
Expected: FAIL — DAO 方法未实现

- [ ] **Step 3: 实现 dao/scholar.py**

替换 `backend/dao/scholar.py`：

```python
"""专家/人才数据查询（MySQL）。"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from db_model.scholar import DwdScholar


class ScholarDAO:
    """dwd_scholar 查询封装。"""

    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, scholar_id: str) -> DwdScholar | None:
        return self._s.get(DwdScholar, scholar_id)

    def list(self, *, limit: int = 100, offset: int = 0) -> Sequence[DwdScholar]:
        return list(
            self._s.execute(select(DwdScholar).limit(limit).offset(offset)).scalars()
        )
```

- [ ] **Step 4: 实现 dao/organization.py**

替换 `backend/dao/dao/organization.py`（注意路径 `backend/dao/organization.py`）：

```python
"""机构/企业数据查询（MySQL）。"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from db_model.organization import DwdOrgRegInfo


class OrganizationDAO:
    """dwd_org_reg_info 查询封装。"""

    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_id(self, org_id: str) -> DwdOrgRegInfo | None:
        return self._s.get(DwdOrgRegInfo, org_id)

    def get_by_name(self, name_cn: str) -> DwdOrgRegInfo | None:
        stmt = select(DwdOrgRegInfo).where(DwdOrgRegInfo.name_cn == name_cn).limit(1)
        return self._s.execute(stmt).scalar_one_or_none()

    def list(self, *, limit: int = 100, offset: int = 0) -> Sequence[DwdOrgRegInfo]:
        return list(
            self._s.execute(select(DwdOrgRegInfo).limit(limit).offset(offset)).scalars()
        )
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd /data1/huyatao/tech-kg-api/backend && .venv/bin/python -m pytest tests/unit/test_dao_scholar.py tests/unit/test_dao_organization.py -v`
Expected: 5 passed

- [ ] **Step 6: ruff + 提交**

```bash
cd /data1/huyatao/tech-kg-api/backend
ruff check dao/scholar.py dao/organization.py tests/unit/test_dao_scholar.py tests/unit/test_dao_organization.py
ruff format dao/scholar.py dao/organization.py tests/unit/test_dao_scholar.py tests/unit/test_dao_organization.py
git add dao/scholar.py dao/organization.py tests/unit/test_dao_scholar.py tests/unit/test_dao_organization.py
git commit -m "feat(dao): implement ScholarDAO and OrganizationDAO"
```

---

## Task 3: graph_db techkg 空间单例

**Files:** Modify `backend/infra/graph_db/__init__.py`; Test `backend/tests/unit/test_graph_db_singleton.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/unit/test_graph_db_singleton.py`：

```python
from __future__ import annotations

import infra.graph_db as graph_pkg
from infra.graph_db import TRSGraphClient, close_techkg_client, get_techkg_client


def test_techkg_singleton_caches_and_resets(monkeypatch):
    monkeypatch.setenv("TRS_GRAPH_BASE_URL", "http://test")
    monkeypatch.setenv("TRS_GRAPH_SPACE", "ignored")  # techkg 固定，忽略 env space
    monkeypatch.setenv("TRS_GRAPH_API_KEY", "")
    close_techkg_client()
    monkeypatch.setattr(TRSGraphClient, "connect", lambda self: None)
    monkeypatch.setattr(TRSGraphClient, "is_connected", lambda self: True)
    c1 = get_techkg_client()
    c2 = get_techkg_client()
    assert c1 is c2
    assert c1._settings.space == "techkg"  # noqa: SLF001
    close_techkg_client()
    assert graph_pkg._techkg_client is None  # noqa: SLF001
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /data1/huyatao/tech-kg-api/backend && .venv/bin/python -m pytest tests/unit/test_graph_db_singleton.py -v`
Expected: FAIL — `get_techkg_client` 不存在

- [ ] **Step 3: 实现 techkg 单例**

在 `backend/infra/graph_db/__init__.py` 末尾追加（保留已有 `get_trs_graph_client`/`close_trs_graph_client`/`_client`/`_client_lock` 不变）：

```python
_techkg_client: TRSGraphClient | None = None


def get_techkg_client() -> TRSGraphClient:
    """techkg 图空间单例（space 固定为 'techkg'，其余读 TRS_GRAPH_* env）。"""
    global _techkg_client
    if _techkg_client is not None:
        return _techkg_client
    with _client_lock:
        if _techkg_client is not None:
            return _techkg_client
        settings = TRSGraphSettings.from_env()
        settings.space = "techkg"
        client = TRSGraphClient(settings)
        client.connect()
        _techkg_client = client
    return _techkg_client


def close_techkg_client() -> None:
    """关闭并释放 techkg 单例。"""
    global _techkg_client
    with _client_lock:
        if _techkg_client is not None:
            _techkg_client.close()
            _techkg_client = None
```

并把 `get_techkg_client`、`close_techkg_client` 加入 `__all__`。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /data1/huyatao/tech-kg-api/backend && .venv/bin/python -m pytest tests/unit/test_graph_db_singleton.py -v`
Expected: 1 passed；且 `tests/unit/test_trs_graph_client.py` 仍 65 passed（无回归）。

- [ ] **Step 5: ruff + 提交**

```bash
cd /data1/huyatao/tech-kg-api/backend
ruff check infra/graph_db/__init__.py tests/unit/test_graph_db_singleton.py && ruff format infra/graph_db/__init__.py tests/unit/test_graph_db_singleton.py
git add infra/graph_db/__init__.py tests/unit/test_graph_db_singleton.py
git commit -m "feat(graph): add techkg space singleton accessor"
```

---

## Task 4: 图 schema 初始化 script/init_graph_schema.py

**Files:** Create `backend/script/init_graph_schema.py`; Test `backend/tests/unit/test_init_graph_schema.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/unit/test_init_graph_schema.py`：

```python
from __future__ import annotations

from script.init_graph_schema import SCHEMA_DDL, CREATE_SPACE_DDL


def test_ddl_contains_tags_and_edge():
    joined = "\n".join(CREATE_SPACE_DDL + SCHEMA_DDL)
    assert "CREATE SPACE IF NOT EXISTS techkg" in joined
    assert "CREATE TAG IF NOT EXISTS Scholar(" in joined
    assert "CREATE TAG IF NOT EXISTS Organization(" in joined
    assert "CREATE EDGE IF NOT EXISTS EMPLOYED_BY(" in joined
    assert "scholar_id string" in joined
    assert "name_cn string" in joined
    assert "relation_type string" in joined
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /data1/huyatao/tech-kg-api/backend && .venv/bin/python -m pytest tests/unit/test_init_graph_schema.py -v`
Expected: FAIL — 模块不存在

- [ ] **Step 3: 实现 script/init_graph_schema.py**

创建 `backend/script/init_graph_schema.py`：

```python
"""初始化 techkg 图空间 schema（幂等）。

先在已存在空间（默认 entity_binding_demo）上下文执行 CREATE SPACE，
再切换到 techkg 执行 TAG/EDGE/INDEX DDL。

用法：python -m script.init_graph_schema
"""

from __future__ import annotations

from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings

# 在任意已存在空间上下文执行（CREATE SPACE 是全局操作）
CREATE_SPACE_DDL: list[str] = [
    "CREATE SPACE IF NOT EXISTS techkg(vid_type=FIXED_STRING(64), partition_num=10, replica_factor=1);",
]

# 在 techkg 空间执行
SCHEMA_DDL: list[str] = [
    "CREATE TAG IF NOT EXISTS Scholar(scholar_id string, name_zh string, name_en string, "
    "scholar_org_name_zh string, scholar_org_name_en string, h_index int64, "
    "citation_nums int64, paper_nums int64);",
    "CREATE TAG IF NOT EXISTS Organization(org_id string, name_cn string, province string, "
    "city string, org_type string, listing_status string, incorporation_year int64);",
    "CREATE EDGE IF NOT EXISTS EMPLOYED_BY(relation_type string, role string, "
    "start_date string, end_date string, source string);",
    "CREATE TAG INDEX IF NOT EXISTS scholar_id_idx ON Scholar(scholar_id(64));",
    "CREATE TAG INDEX IF NOT EXISTS org_name_idx ON Organization(name_cn(128));",
    "CREATE TAG INDEX IF NOT EXISTS org_id_idx ON Organization(org_id(64));",
    "CREATE EDGE INDEX IF NOT EXISTS employed_by_idx ON EMPLOYED_BY();",
]


def init_schema() -> None:
    settings = TRSGraphSettings.from_env()
    # 1) 在默认空间上下文建 techkg 空间
    bootstrap = TRSGraphClient(settings)
    bootstrap.connect()
    try:
        for stmt in CREATE_SPACE_DDL:
            bootstrap.execute_write(stmt)
    finally:
        bootstrap.close()
    # 2) 切到 techkg 建 schema
    techkg = TRSGraphClient(settings)
    techkg._settings.space = "techkg"  # noqa: SLF001
    techkg.connect()
    try:
        for stmt in SCHEMA_DDL:
            techkg.execute_write(stmt)
    finally:
        techkg.close()


if __name__ == "__main__":
    init_schema()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /data1/huyatao/tech-kg-api/backend && .venv/bin/python -m pytest tests/unit/test_init_graph_schema.py -v`
Expected: 1 passed

- [ ] **Step 5: 在真实图库执行一次建 schema（可选验证）**

Run: `cd /data1/huyatao/tech-kg-api/backend && TRS_GRAPH_BASE_URL=http://localhost:8090 TRS_GRAPH_SPACE=entity_binding_demo TRS_GRAPH_API_KEY=ysukeg .venv/bin/python -m script.init_graph_schema`
Expected: 无异常退出。若 CREATE SPACE 在该服务下不被允许，记录报错并在执行阶段调整（可能需服务端建空间）。

- [ ] **Step 6: ruff + 提交**

```bash
cd /data1/huyatao/tech-kg-api/backend
ruff check script/init_graph_schema.py tests/unit/test_init_graph_schema.py && ruff format script/init_graph_schema.py tests/unit/test_init_graph_schema.py
git add script/init_graph_schema.py tests/unit/test_init_graph_schema.py
git commit -m "feat(graph): add techkg schema init script"
```

---

## Task 5: ETL script/load_graph.py

**Files:** Create `backend/script/load_graph.py`; Test `backend/tests/unit/test_load_graph.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/unit/test_load_graph.py`：

```python
from __future__ import annotations

from unittest.mock import MagicMock

from script.load_graph import build_scholar_node_props, build_org_node_props, load_graph


def test_build_scholar_node_props():
    s = MagicMock(scholar_id="S1", name_zh="张伟", name_en="Zhang", scholar_org_name_zh="清华大学",
                   scholar_org_name_en="Tsinghua", h_index=10, citation_nums=100, paper_nums=5)
    p = build_scholar_node_props(s)
    assert p == {"scholar_id": "S1", "name_zh": "张伟", "name_en": "Zhang",
                 "scholar_org_name_zh": "清华大学", "scholar_org_name_en": "Tsinghua",
                 "h_index": 10, "citation_nums": 100, "paper_nums": 5}


def test_build_org_node_props():
    o = MagicMock(org_id="O1", name_cn="清华大学", province="北京市", city="北京",
                  org_type="高校", listing_status="", incorporation_year=1911)
    p = build_org_node_props(o)
    assert p["org_id"] == "O1" and p["name_cn"] == "清华大学" and p["province"] == "北京市"


def test_load_graph_empty_mysql(monkeypatch):
    # MySQL 空：scholar/org 都返回空，graph 不应被写入
    graph = MagicMock()
    graph.create_node = MagicMock()
    graph.create_edge = MagicMock()
    graph.find_nodes = MagicMock(return_value=MagicMock(items=[]))

    class FakeScholarDAO:
        def __init__(self, *a, **k): pass
        def list(self, *, limit, offset): return []
    class FakeOrgDAO:
        def __init__(self, *a, **k): pass
        def list(self, *, limit, offset): return []
        def get_by_name(self, name): return None

    monkeypatch.setattr("script.load_graph.ScholarDAO", FakeScholarDAO)
    monkeypatch.setattr("script.load_graph.OrganizationDAO", FakeOrgDAO)
    monkeypatch.setattr("script.load_graph.get_techkg_client", lambda: graph)
    monkeypatch.setattr("script.load_graph.get_mysql_client", lambda: MagicMock())

    n = load_graph()
    assert n == 0
    graph.create_node.assert_not_called()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /data1/huyatao/tech-kg-api/backend && .venv/bin/python -m pytest tests/unit/test_load_graph.py -v`
Expected: FAIL — 模块不存在

- [ ] **Step 3: 实现 script/load_graph.py**

创建 `backend/script/load_graph.py`：

```python
"""MySQL → techkg 图 ETL：灌 Scholar、Organization 节点与 EMPLOYED_BY 边。

用法：python -m script.load_graph
"""

from __future__ import annotations

import logging

from dao.organization import OrganizationDAO
from dao.scholar import ScholarDAO
from infra.graph_db import get_techkg_client
from infra.mysql import get_mysql_client

logger = logging.getLogger("script.load_graph")


def build_scholar_node_props(s) -> dict:
    return {
        "scholar_id": s.scholar_id,
        "name_zh": s.name_zh or "",
        "name_en": s.name_en or "",
        "scholar_org_name_zh": s.scholar_org_name_zh or "",
        "scholar_org_name_en": s.scholar_org_name_en or "",
        "h_index": s.h_index or 0,
        "citation_nums": s.citation_nums or 0,
        "paper_nums": s.paper_nums or 0,
    }


def build_org_node_props(o) -> dict:
    return {
        "org_id": o.org_id,
        "name_cn": o.name_cn or "",
        "province": o.province or "",
        "city": o.city or "",
        "org_type": o.org_type or "",
        "listing_status": o.listing_status or "",
        "incorporation_year": o.incorporation_year or 0,
    }


def load_graph(batch_limit: int = 500) -> int:
    """灌图，返回写入的 Scholar 节点数。MySQL 空时返回 0。"""
    mysql = get_mysql_client()
    graph = get_techkg_client()

    session = mysql.session()
    scholar_dao = ScholarDAO(session)
    org_dao = OrganizationDAO(session)

    # 1) Organization 节点（先灌，便于边匹配）
    orgs = org_dao.list(limit=100000)
    org_name_to_id: dict[str, object] = {}
    for o in orgs:
        node = graph.create_node(["Organization"], build_org_node_props(o))
        org_name_to_id[o.name_cn] = node.id
        # 同时按 org_id 缓存
    # 2) Organization 按 org_id 再建索引映射（find_nodes 兜底）
    # 3) Scholar 节点 + EMPLOYED_BY 边
    count = 0
    offset = 0
    while True:
        scholars = scholar_dao.list(limit=batch_limit, offset=offset)
        if not scholars:
            break
        for s in scholars:
            snode = graph.create_node(["Scholar"], build_scholar_node_props(s))
            count += 1
            org_name = s.scholar_org_name_zh or ""
            org_id = org_name_to_id.get(org_name)
            if org_id is None and org_name:
                found = graph.find_nodes(["Organization"], {"name_cn": org_name}, limit=1)
                if found.items:
                    org_id = found.items[0].id
                    org_name_to_id[org_name] = org_id
            if org_id is not None:
                graph.create_edge(
                    snode.id, org_id, "EMPLOYED_BY",
                    {"relation_type": "任职", "role": "", "start_date": "", "end_date": "", "source": "mysql"},
                )
        offset += len(scholars)
        if len(scholars) < batch_limit:
            break
    session.close()
    logger.info("loaded %d scholars, %d orgs", count, len(orgs))
    return count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    load_graph()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /data1/huyatao/tech-kg-api/backend && .venv/bin/python -m pytest tests/unit/test_load_graph.py -v`
Expected: 3 passed

- [ ] **Step 5: ruff + 提交**

```bash
cd /data1/huyatao/tech-kg-api/backend
ruff check script/load_graph.py tests/unit/test_load_graph.py && ruff format script/load_graph.py tests/unit/test_load_graph.py
git add script/load_graph.py tests/unit/test_load_graph.py
git commit -m "feat(graph): add MySQL->techkg ETL loader"
```

---

## Task 6: 请求/响应 Pydantic schemas

**Files:** Create `backend/biz/schemas/expert_enterprise_relation.py`; Test `backend/tests/unit/test_expert_enterprise_schemas.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/unit/test_expert_enterprise_schemas.py`：

```python
from __future__ import annotations

from biz.schemas.expert_enterprise_relation import (
    EnterpriseItem,
    ExpertEnterpriseBuildRequest,
    ExpertEnterpriseBuildResponse,
    TimeRange,
)


def test_request_defaults_and_parse():
    req = ExpertEnterpriseBuildRequest(expertAId="S1")
    assert req.dataSource == "all"
    assert req.relationType == "all"
    assert req.timeRange is None


def test_response_assemble():
    resp = ExpertEnterpriseBuildResponse(
        status="success",
        expert="张伟",
        expert_id="S1",
        title="",
        enterprises=[EnterpriseItem(enterprise_id="O1", name="清华大学", relation="任职")],
    )
    assert resp.enterprises[0].relation == "任职"
    assert resp.status == "success"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /data1/huyatao/tech-kg-api/backend && .venv/bin/python -m pytest tests/unit/test_expert_enterprise_schemas.py -v`
Expected: FAIL — 模块不存在

- [ ] **Step 3: 实现 schemas**

创建 `backend/biz/schemas/__init__.py`（空）和 `backend/biz/schemas/expert_enterprise_relation.py`：

```python
"""专家-企业关系构建 请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TimeRange(BaseModel):
    start: str | None = None
    end: str | None = None


class ExpertEnterpriseBuildRequest(BaseModel):
    dataSource: str = "all"
    expertAId: str
    relationType: str = "all"
    timeRange: TimeRange | None = None


class EnterpriseItem(BaseModel):
    enterprise_id: str
    name: str
    type: str = ""
    province: str = ""
    relation: str = ""
    role: str = ""
    start_date: str = ""
    end_date: str = ""


class ExpertEnterpriseBuildResponse(BaseModel):
    status: str = "success"
    expert: str | None = None
    expert_id: str | None = None
    title: str | None = None
    enterprises: list[EnterpriseItem] = Field(default_factory=list)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /data1/huyatao/tech-kg-api/backend && .venv/bin/python -m pytest tests/unit/test_expert_enterprise_schemas.py -v`
Expected: 2 passed

- [ ] **Step 5: ruff + 提交**

```bash
cd /data1/huyatao/tech-kg-api/backend
ruff check biz/schemas tests/unit/test_expert_enterprise_schemas.py && ruff format biz/schemas tests/unit/test_expert_enterprise_schemas.py
git add biz/schemas tests/unit/test_expert_enterprise_schemas.py
git commit -m "feat(graph): add expert-enterprise request/response schemas"
```

---

## Task 7: service / application / handler 实现 build

**Files:** Modify `backend/service/expert_enterprise_relation.py`, `backend/application/expert_enterprise_relation.py`, `backend/biz/handler/expert_enterprise_relation.py`; Test `backend/tests/unit/test_expert_enterprise_service.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/unit/test_expert_enterprise_service.py`：

```python
from __future__ import annotations

from unittest.mock import MagicMock

from service.expert_enterprise_relation import ExpertEnterpriseRelationService


def _graph_with_expert_and_org():
    graph = MagicMock()
    scholar_node = MagicMock(id="S1", labels=["Scholar"], properties={
        "scholar_id": "S1", "name_zh": "张伟", "scholar_org_name_zh": "清华大学"})
    org_node = MagicMock(id="O1", labels=["Organization"], properties={
        "org_id": "O1", "name_cn": "清华大学", "province": "北京市", "org_type": "高校"})
    edge = MagicMock(id="S1->O1@0", type="EMPLOYED_BY", source_id="S1", target_id="O1",
                     properties={"relation_type": "任职", "role": "", "start_date": "", "end_date": ""})
    graph.find_nodes = MagicMock(side_effect=lambda labels, props, **k: (
        MagicMock(items=[scholar_node]) if "Scholar" in labels else MagicMock(items=[org_node])
    ))
    graph.get_node_edges = MagicMock(return_value=[edge])
    graph.get_node = MagicMock(return_value=org_node)
    return graph


def test_build_returns_expert_and_enterprises():
    svc = ExpertEnterpriseRelationService()
    svc._graph = _graph_with_expert_and_org()  # noqa: SLF001
    resp = svc.build({"expertAId": "S1", "relationType": "all", "dataSource": "all", "timeRange": None})
    assert resp["status"] == "success"
    assert resp["expert"] == "张伟"
    assert resp["expert_id"] == "S1"
    assert resp["enterprises"][0]["name"] == "清华大学"
    assert resp["enterprises"][0]["relation"] == "任职"


def test_build_expert_not_found():
    graph = MagicMock()
    graph.find_nodes = MagicMock(return_value=MagicMock(items=[]))
    svc = ExpertEnterpriseRelationService()
    svc._graph = graph  # noqa: SLF001
    resp = svc.build({"expertAId": "ZZZ", "relationType": "all", "dataSource": "all", "timeRange": None})
    assert resp["status"] == "success"
    assert resp["expert"] is None
    assert resp["enterprises"] == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /data1/huyatao/tech-kg-api/backend && .venv/bin/python -m pytest tests/unit/test_expert_enterprise_service.py -v`
Expected: FAIL — `build` 不存在

- [ ] **Step 3: 实现 service**

替换 `backend/service/expert_enterprise_relation.py`：

```python
"""专家-企业关系构建服务（查 techkg 图）。"""

from __future__ import annotations

from typing import Any

from infra.graph_db import TRSGraphClient, get_techkg_client
from service.base_module import KGModuleScaffoldService


class ExpertEnterpriseRelationService(KGModuleScaffoldService):
    module_code = "expert_enterprise_relation"

    def __init__(self) -> None:
        super().__init__()
        self._graph: TRSGraphClient | None = None

    def _client(self) -> TRSGraphClient:
        if self._graph is None:
            self._graph = get_techkg_client()
        return self._graph

    def build(self, payload: dict[str, Any]) -> dict[str, Any]:
        expert_a_id = payload.get("expertAId", "")
        relation_type = payload.get("relationType", "all")
        time_range = payload.get("timeRange") or {}
        graph = self._client()

        # 1) 按 scholar_id 找专家节点
        found = graph.find_nodes(["Scholar"], {"scholar_id": expert_a_id}, limit=1)
        if not found.items:
            return {"status": "success", "expert": None, "expert_id": expert_a_id, "title": None, "enterprises": []}
        scholar = found.items[0]
        props = scholar.properties

        # 2) 取 EMPLOYED_BY 边
        edges = graph.get_node_edges(scholar.id, direction="out", edge_type="EMPLOYED_BY", limit=100)
        enterprises: list[dict[str, Any]] = []
        for e in edges:
            if relation_type and relation_type != "all":
                if e.properties.get("relation_type", "任职") != relation_type:
                    continue
            org = graph.get_node(e.target_id)
            if org is None:
                continue
            op = org.properties
            enterprises.append({
                "enterprise_id": str(op.get("org_id", org.id)),
                "name": op.get("name_cn", "") or "",
                "type": op.get("org_type", "") or "",
                "province": op.get("province", "") or "",
                "relation": e.properties.get("relation_type", "任职"),
                "role": e.properties.get("role", "") or "",
                "start_date": e.properties.get("start_date", "") or "",
                "end_date": e.properties.get("end_date", "") or "",
            })

        return {
            "status": "success",
            "expert": props.get("name_zh") or None,
            "expert_id": props.get("scholar_id") or expert_a_id,
            "title": "",  # dwd_scholar 无职称字段，暂空
            "enterprises": enterprises,
        }
```

- [ ] **Step 4: 实现 application**

替换 `backend/application/expert_enterprise_relation.py`：

```python
"""专家-企业关系构建 编排层。"""

from __future__ import annotations

from typing import Any

from service.expert_enterprise_relation import ExpertEnterpriseRelationService


class ExpertEnterpriseRelationApplication:
    def __init__(self) -> None:
        self._service = ExpertEnterpriseRelationService()

    def describe(self) -> dict[str, object]:
        return self._service.describe()

    def build(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._service.build(payload)
```

- [ ] **Step 5: 实现 handler**

替换 `backend/biz/handler/expert_enterprise_relation.py`：

```python
"""专家-企业关系构建 路由。"""

from fastapi import APIRouter

from application.expert_enterprise_relation import ExpertEnterpriseRelationApplication
from biz.schemas.expert_enterprise_relation import ExpertEnterpriseBuildRequest

router = APIRouter(prefix="/kg-construction/expert-enterprise-relations")
application = ExpertEnterpriseRelationApplication()


@router.get("")
async def describe_expert_enterprise_relation() -> dict[str, object]:
    return application.describe()


@router.post("/build")
async def build_expert_enterprise_relation(
    req: ExpertEnterpriseBuildRequest,
) -> dict[str, object]:
    return application.build(req.model_dump())
```

- [ ] **Step 6: 跑测试确认通过**

Run: `cd /data1/huyatao/tech-kg-api/backend && .venv/bin/python -m pytest tests/unit/test_expert_enterprise_service.py -v`
Expected: 2 passed

- [ ] **Step 7: 确认 app 可导入 + 既有测试不破**

Run: `cd /data1/huyatao/tech-kg-api/backend && .venv/bin/python -c "from main import app; print('ok')"`
Run: `cd /data1/huyatao/tech-kg-api/backend && .venv/bin/python -m pytest tests/integration/test_health.py -q`
Expected: `ok`；2 passed

- [ ] **Step 8: ruff + 提交**

```bash
cd /data1/huyatao/tech-kg-api/backend
ruff check service/expert_enterprise_relation.py application/expert_enterprise_relation.py biz/handler/expert_enterprise_relation.py tests/unit/test_expert_enterprise_service.py
ruff format service/expert_enterprise_relation.py application/expert_enterprise_relation.py biz/handler/expert_enterprise_relation.py tests/unit/test_expert_enterprise_service.py
git add service/expert_enterprise_relation.py application/expert_enterprise_relation.py biz/handler/expert_enterprise_relation.py tests/unit/test_expert_enterprise_service.py
git commit -m "feat(graph): implement expert-enterprise build API (handler/app/service)"
```

---

## Task 8: API 集成测试（external）

**Files:** Create `backend/tests/integration/test_expert_enterprise_api.py`

- [ ] **Step 1: 写集成测试**

创建 `backend/tests/integration/test_expert_enterprise_api.py`：

```python
"""专家-企业关系构建 API 集成测试（需真实后端 + techkg 图，@external）。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.external
class TestExpertEnterpriseAPI:
    @pytest.mark.asyncio
    async def test_build_returns_shape(self):
        async with AsyncClient(transport=ASGITransport(app=__import__("main").app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/kg-construction/expert-enterprise-relations/build", json={
                "dataSource": "all", "expertAId": "talent_001", "relationType": "all", "timeRange": None})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert isinstance(data["enterprises"], list)
        assert "expert_id" in data
```

- [ ] **Step 2: 跑（无图数据时返回空 success，不报错）**

Run: `cd /data1/huyatao/tech-kg-api/backend && .venv/bin/python -m pytest tests/integration/test_expert_enterprise_api.py -v`
Expected: PASS（图空时 `enterprises=[]`，status=success）。若 techkg 空间/schema 不存在导致 500，先跑 Task 4 Step 5 建 schema。

- [ ] **Step 3: ruff + 提交**

```bash
cd /data1/huyatao/tech-kg-api/backend
ruff check tests/integration/test_expert_enterprise_api.py && ruff format tests/integration/test_expert_enterprise_api.py
git add tests/integration/test_expert_enterprise_api.py
git commit -m "test(graph): add expert-enterprise API integration test"
```

---

## Task 9: 前端接线 + vite 代理修正 + 构建验证

**Files:** Modify `frontend/src/App.vue`, `frontend/vite.config.ts`

- [ ] **Step 1: 修 vite 代理（不 strip /api）**

读 `frontend/vite.config.ts`，把 `rewrite: (path) => path.replace(/^\/api/, '')` 这行删除（让 `/api/v1/...` 原样转发到后端）。改后 server.proxy 部分：

```python
    server: {
      proxy: {
        "/api": {
          target: env.VITE_API_TARGET || "http://localhost:8100",
          changeOrigin: true,
        },
      },
    },
```

- [ ] **Step 2: 改 App.vue apiPath + 加 fetch**

在 `frontend/src/App.vue`：
- 把 `relationFeatures` 里"专家-企业关系构建"那项的 `apiPath` 从 `/api/v1/enterprise/relation/build` 改为 `/api/v1/kg-construction/expert-enterprise-relations/build`。
- 在 `<script setup>` 内加一个加载函数与状态（放在 `graphNodes` 定义之后）：

```ts
const loading = ref(false)
const apiError = ref('')

async function loadEnterpriseRelation() {
  if (currentSubFunction.value.featureName !== '专家-企业关系构建') return
  loading.value = true
  apiError.value = ''
  try {
    const resp = await fetch(currentApiPath.value, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        dataSource: params.value.dataSource === '全部数据源' ? 'all' : params.value.dataSource,
        expertAId: params.value.expertAId,
        relationType: params.value.relationType === '全部关系' ? 'all' : params.value.relationType,
        timeRange: { start: params.value.start, end: params.value.end },
      }),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const data = await resp.json()
    if (data.expert) {
      // 用真实数据替换图节点：中心专家 + 企业节点
      graphNodes.value = [
        { key: 'expert', title: `专家：${data.expert}`, subtitle: data.title || '', x: 412, y: 292, width: 300, height: 94, kind: 'expert' },
        ...data.enterprises.slice(0, 5).map((e: any, i: number) => ({
          key: (`company${i + 1}` as GraphNodeKey),
          title: `企业${i + 1}：${e.name}`,
          subtitle: e.type || '企业',
          relation: e.relation || '',
          x: 35 + (i % 3) * 360, y: 45 + Math.floor(i / 3) * 250, width: 360, height: 110, kind: 'company' as const,
        })),
      ]
    }
  } catch (e: any) {
    apiError.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}
```

- 在触发构建的地方调用（如切换到该子功能或点击运行按钮时）。若 UI 无明确按钮，可在 `watch` 到 `activeSubFunctionName` 变为"专家-企业关系构建"时调用：

```ts
import { watch } from 'vue'
watch(activeSubFunctionName, (v) => { if (v === '专家-企业关系构建') loadEnterpriseRelation() })
```

（把 `import { computed, ref } from 'vue'` 改为 `import { computed, ref, watch } from 'vue'`。）

- [ ] **Step 3: 构建验证**

```bash
cd /data1/huyatao/tech-kg-api/frontend
pnpm build
```
Expected: `vue-tsc -b` 无类型错误，`vite build` 成功。

- [ ] **Step 4: 启动后端 + 前端联调（人工）**

后端：`.venv/bin/python -m uvicorn main:app --port 8100`（或 `--reload`）。前端：`pnpm dev`。浏览器开 dev server，切到"专家-企业关系构建"，观察 fetch 调用与返回（图空时 enterprises=[]，界面显示中心专家或空）。

- [ ] **Step 5: 提交**

```bash
cd /data1/huyatao/tech-kg-api
git add frontend/src/App.vue frontend/vite.config.ts
git commit -m "feat(frontend): wire expert-enterprise relation to real API"
```

---

## Task 10: 全量校验

**Files:** 无（校验）

- [ ] **Step 1: 全量后端测试**

Run: `cd /data1/huyatao/tech-kg-api/backend && .venv/bin/python -m pytest -q`
Expected: 全部单测 passed；external 集成测试 skip 或空通过。

- [ ] **Step 2: ruff 全量**

Run: `cd /data1/huyatao/tech-kg-api/backend && ruff check . && ruff format --check .`
Expected: All checks passed。

- [ ] **Step 3: 前端构建**

Run: `cd /data1/huyatao/tech-kg-api/frontend && pnpm build`
Expected: 成功。

- [ ] **Step 4: 真实图 schema + ETL 端到端（MySQL 空）**

```bash
cd /data1/huyatao/tech-kg-api/backend
TRS_GRAPH_BASE_URL=http://localhost:8090 TRS_GRAPH_SPACE=entity_binding_demo TRS_GRAPH_API_KEY=ysukeg .venv/bin/python -m script.init_graph_schema
TRS_GRAPH_BASE_URL=http://localhost:8090 TRS_GRAPH_API_KEY=ysukeg .venv/bin/python -m script.load_graph
```
Expected: init 成功；load 打印 "loaded 0 scholars, 0 orgs"（MySQL 空）。API `POST /build` 返回 `enterprises=[]`。

- [ ] **Step 5: 最终提交（若有格式微调）**

```bash
cd /data1/huyatao/tech-kg-api
git status
git add -A && git commit -m "chore(graph): final lint and validation pass" || echo "nothing to commit"
```

---

## 自审

- **Spec 覆盖**：§3 图 schema→Task 4；§4 MySQL 接入→Task 1+2；§5 ETL→Task 5；§6 API 契约→Task 6+7+8；§7 前端→Task 9；§10 阶段→Task 1-10 对应；§11 验收→Task 10。全覆盖。
- **占位符**：无 TBD；每步有可执行命令与完整代码。
- **类型/命名一致性**：`build_db_url`/`MySQLClient`/`get_mysql_client`/`get_session`（Task1）在 Task2/5 复用一致；`ScholarDAO.get/list`、`OrganizationDAO.get_by_id/get_by_name/list`（Task2）在 Task5 复用一致；`get_techkg_client`/`close_techkg_client`/`_techkg_client`（Task3）在 Task5/7 复用一致；`ExpertEnterpriseBuildRequest/Response/EnterpriseItem`（Task6）在 Task7 handler 复用一致；service.build payload 用 dict（handler 用 `req.model_dump()`）一致；响应字段 `expert/expert_id/title/enterprises/status` 在 Task7 与 spec §6 一致。
