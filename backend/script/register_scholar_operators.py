"""批量把学者领域算子注册到工作流平台。

用法::

    # 只上传，不调用
    uv run python -m script.register_scholar_operators

    # 上传后触发 dry-run 调用做冒烟测试
    uv run python -m script.register_scholar_operators --invoke

设计说明：
- 源码来源：``backend/operators/scholar/user.scholar.*.py``（本目录之外，源码不参与
  运行时加载，只是 git 侧的"可读版本"）
- 上传目标：本地 FastAPI 应用的 ``/api/v1/operators``（通过 ASGI transport 进程内调用，
  等价于外部厂商用 HTTP 上传）
- 已存在的算子走 PUT，走热更新；新算子走 POST

按新规则，本脚本只调用 FastAPI 已经暴露的算子接口，不直接触碰 OperatorRegistry。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_OPERATORS_DIR = Path(__file__).resolve().parents[1] / "operators" / "scholar"

# 算子名 → (相对文件路径, kind, description)
_OPERATOR_DEFS: list[dict[str, str]] = [
    {
        "name": "user.scholar.load_entities",
        "file": "user.scholar.load_entities.py",
        "kind": "entity_extraction",
        "description": "学者实体抽取：从 dwd_scholar 生成 Person 顶点",
    },
    {
        "name": "user.scholar.load_relations",
        "file": "user.scholar.load_relations.py",
        "kind": "relation_extraction",
        "description": "学者关系抽取：AFFILIATED_WITH + COAUTHOR_WITH（可选 AUTHORED_BY 兜底）",
    },
    {
        "name": "user.scholar.build_milvus_index",
        "file": "user.scholar.build_milvus_index.py",
        "kind": "data_processing",
        "description": "学者 Milvus 索引：Person 顶点稠密+BM25 双编码入库",
    },
    {
        "name": "user.scholar.align_affiliations",
        "file": "user.scholar.align_affiliations.py",
        "kind": "entity_ingestion",
        "description": "学者机构对齐：桩机构 → 真实机构 SAME_AS 边",
    },
    {
        "name": "user.scholar.dedupe_persons",
        "file": "user.scholar.dedupe_persons.py",
        "kind": "entity_ingestion",
        "description": "学者消歧：Person 对综合打分 + SAME_AS 写边/报表",
    },
]
_VERSION = "1.0.0"


async def _register_one(
    client: httpx.AsyncClient,
    definition: dict[str, str],
) -> dict[str, object]:
    source_path = _OPERATORS_DIR / definition["file"]
    if not source_path.exists():
        raise FileNotFoundError(f"算子源码不存在: {source_path}")
    source = source_path.read_text(encoding="utf-8")
    payload = {
        "name": definition["name"],
        "version": _VERSION,
        "kind": definition["kind"],
        "description": definition["description"],
        "source": source,
    }
    # 已存在则走 PUT，否则 POST
    get_resp = await client.get(f"/api/v1/operators/{definition['name']}")
    if get_resp.status_code == 200:
        put_payload = {
            "version": _VERSION,
            "kind": definition["kind"],
            "description": definition["description"],
            "source": source,
        }
        resp = await client.put(f"/api/v1/operators/{definition['name']}", json=put_payload)
        action = "updated"
    elif get_resp.status_code == 404:
        resp = await client.post("/api/v1/operators", json=payload)
        action = "created"
    else:
        resp = get_resp
        action = "check_failed"
    if resp.status_code not in {200, 201}:
        raise RuntimeError(
            f"注册 {definition['name']} 失败: HTTP {resp.status_code} body={resp.text}"
        )
    return {"name": definition["name"], "action": action, "manifest": resp.json()}


async def _invoke_dry_run(
    client: httpx.AsyncClient,
    definition: dict[str, str],
) -> dict[str, object]:
    body = {"data": [], "ctx": {"dry_run": True}}
    resp = await client.post(f"/api/v1/operators/{definition['name']}/invoke", json=body)
    payload = resp.json()
    return {
        "name": definition["name"],
        "status_code": resp.status_code,
        "count": payload.get("count") if isinstance(payload, dict) else None,
        "data": payload.get("data") if isinstance(payload, dict) else payload,
    }


async def _run(*, invoke: bool) -> int:
    from main import app  # noqa: WPS433 - 延迟导入避免循环

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://kg-internal") as client:
        registered: list[dict[str, object]] = []
        for definition in _OPERATOR_DEFS:
            result = await _register_one(client, definition)
            print(f"[REGISTER] {result['action']:8s} {result['name']}")
            registered.append(result)

        if invoke:
            print("\n=== dry-run invoke ===")
            for definition in _OPERATOR_DEFS:
                result = await _invoke_dry_run(client, definition)
                status_ok = result["status_code"] == 200 and result["data"]
                first = (result["data"] or [{}])[0] if isinstance(result["data"], list) else {}
                summary = first.get("status") if isinstance(first, dict) else "unknown"
                print(
                    f"[INVOKE]   HTTP {result['status_code']:3d} "
                    f"{'OK' if status_ok else 'FAIL':4s} "
                    f"{definition['name']}  status={summary}"
                )
                if not status_ok:
                    print(json.dumps(result["data"], ensure_ascii=False, indent=2)[:600])

    print(f"\n注册完成：{len(registered)} 个学者算子")
    return 0


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--invoke",
        action="store_true",
        help="上传后触发一次 dry-run 调用做冒烟测试",
    )
    return ap.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse_args()
    return asyncio.run(_run(invoke=args.invoke))


if __name__ == "__main__":
    sys.exit(main())
