"""One-relation extractor: LEGAL_REP_OF（Person → Organization）.

复刻旧 organization_relation_etl.py 口径：法定代表人边：机构基础/研究院/台湾企业 3 张表，person 端用实体侧统一公式。
确定性 rank 幂等，端点验存，虚拟源行过滤；关系脚本一律不建顶点。

Dual-mode 入口：
- CLI: ``python -m script.relation_extractors_one_relation.legal_rep_of_relation --dry-run --limit 1``
- Temporal workflow: 脚本顶层 ``workflow(payload)`` 函数，由
  ``service/temporal_workflows.py:execute_python_script`` Activity 子进程加载并调用。
  payload key 用 snake_case（跟 argparse 转换后的 vars(args) 同形态）。
"""

from typing import Any

from script.relation_extractors_one_relation.common import common_args_from_payload
from script.relation_extractors_one_relation.org_edges import org_relation_cli, run_org_relation

RELATION_KEY = "legal_representative"


def main() -> None:
    org_relation_cli(RELATION_KEY)


def workflow(payload: dict[str, Any]) -> dict[str, Any]:
    """Temporal workflow 入口；payload 同 main() 的 vars(args) 形态。"""
    common = common_args_from_payload(payload)
    table = payload.get("table")
    return run_org_relation(
        RELATION_KEY,
        database=common["database"],
        batch_size=common["batch_size"],
        limit=common["limit"],
        dry_run=common["dry_run"],
        ingest_batch=common["ingest_batch"],
        since=common["since"],
        table=None if table in (None, "all") else str(table),
    )


if __name__ == "__main__":
    main()
