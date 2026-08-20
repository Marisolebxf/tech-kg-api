"""生成科技专家同事关系演示数据，并同步到 TRSGraph。

脚本只更新 ``dwd_scholar`` 的现有字段，不建表、不改表结构、不新增学者。
默认直接写入 MySQL 和图空间；显式传 ``--dry-run`` 时只预览。写入前会在当前目录
保存 JSON 快照，便于定位和恢复被更新的行。

每 15 名专家共用同一机构、部门和重叠任职期；默认 300 人形成 20 个可查询的
同事关系簇。图的 VID、溯源字段、置信度和 ``AFFILIATED_WITH`` 边写入方式沿用仓库现有约定；
相关建边与属性同步全部封装在本脚本内，不修改或调用原关系脚本。

用法（在 backend 目录执行）::

    # 直接写入 MySQL 和 dev 图空间；需要预览时添加 --dry-run
    MYSQL_DATABASE=gkx_element TRS_GRAPH_SPACE=dev \
      uv run python -m script.seed_expert_colleague_demo
    uv run python -m script.seed_expert_colleague_demo --dry-run

"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, inspect, text

from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings
from infra.mysql import MySQLClient
from script.load_scholar_entities import person_vid
from script.scholar_provenance import (
    CONFIDENCE_SOURCE_PRIMARY_KEY,
    confidence_props,
    organization_provenance,
)

logger = logging.getLogger("script.seed_expert_colleague_demo")

DEMO_SOURCE = "expert_colleague_demo_seed"
DEFAULT_PAGE_SCHOLAR_IDS = ("0209a7v6", "1S5195f4")
FIELDS = (
    "scholar_org_name_zh",
    "scholar_org_name_en",
    "work_experience_date",
    "work_experience_institution_en",
    "work_experience_department_en",
    "work_experience_position_en",
    "work_experience_institution_zh",
    "work_experience_department_zh",
    "work_experience_position_zh",
)

ORGANIZATIONS = (
    (
        "colleague_tsinghua_cs",
        "清华大学计算机科学与技术系",
        "Department of Computer Science and Technology, Tsinghua University",
    ),
    (
        "00a94a6adc3c65b318b7aeb0ea240ef9",
        "北京航空材料研究院股份有限公司",
        "Beijing Institute of Aeronautical Materials",
    ),
    (
        "000213e718b09bd45e71789553cc53d7",
        "新智认知数字科技股份有限公司",
        "New Intelligence Cognitive Digital Technology",
    ),
    ("028b0a4ebfb6ecaf48288dbd14272b33", "金能科技股份有限公司", "Jinneng Science and Technology"),
    (
        "02c54b80822a08444c66d4f8be9d5304",
        "深圳市劲拓自动化设备股份有限公司",
        "Shenzhen JT Automation Equipment",
    ),
    (
        "03226042bc98f15da8af47dfef8c3612",
        "上海雅创电子集团股份有限公司",
        "Shanghai Yachuang Electronics Group",
    ),
    ("04396b49d8e61600c5df4122d01255d4", "东方财富信息股份有限公司", "East Money Information"),
    (
        "047583dfefe252480e530d15c0d436df",
        "徐工集团工程机械股份有限公司",
        "XCMG Construction Machinery",
    ),
    ("04b75452bd230e38bd160bb12c13ce9e", "深圳市英威腾电气股份有限公司", "Shenzhen INVT Electric"),
    (
        "059513c5797a1d7a3dfc8f8869c121d9",
        "上海优宁维生物科技股份有限公司",
        "Shanghai Universal Biotech",
    ),
    (
        "015e387d77361b95b2f6953a92059510",
        "广东冠豪高新技术股份有限公司",
        "Guangdong Guanhao High-Tech",
    ),
    ("030a43e4f28dc85ff8e151f6006ff139", "深圳市意天科技有限公司", "Shenzhen Yitian Technology"),
    ("04305390561d54bd193d03223b74c9ab", "金徽矿业股份有限公司", "Jinhui Mining"),
    (
        "0450afbd6e538fc350907b69806a91a5",
        "四川安宁铁钛股份有限公司",
        "Sichuan Anning Iron and Titanium",
    ),
    (
        "045d4a9b4621c5ef43acc5843955a157",
        "宁夏凯添燃气发展股份有限公司",
        "Ningxia Kaitian Gas Development",
    ),
    ("04f92753c7f5da3b263b4fcc0f63adf9", "曼卡龙珠宝股份有限公司", "MCLON Jewellery"),
    ("057bd3d003c92ce097d82d9beeba3e2d", "江苏徐矿能源股份有限公司", "Jiangsu Xukuang Energy"),
    (
        "0344e298274b97c8d5ae73c4ca56d7eb",
        "法狮龙家居建材股份有限公司",
        "Fsilon Home Building Materials",
    ),
    (
        "040dd8acf11fa9dd34b6a4d85d5a1a81",
        "深圳前海骁客影像科技设计有限公司",
        "Shenzhen Qianhai Imaging Technology",
    ),
    (
        "023119200749b21a0bf6d49380499ce8",
        "濠江測試數碼有限公司033",
        "MACAO DEMO DIGITAL LIMITED 033",
    ),
)
DEPARTMENTS = (
    ("智能计算研究室", "Intelligent Computing Laboratory"),
    ("知识工程研究室", "Knowledge Engineering Laboratory"),
    ("数据智能研究室", "Data Intelligence Laboratory"),
    ("协同创新研究室", "Collaborative Innovation Laboratory"),
)
POSITIONS = (
    ("助理研究员", "Assistant Researcher"),
    ("副研究员", "Associate Researcher"),
    ("研究员", "Researcher"),
)


@dataclass(frozen=True)
class DemoExperience:
    scholar_id: str
    organization_id: str
    organization_zh: str
    organization_en: str
    department_zh: str
    department_en: str
    position_zh: str
    position_en: str
    period: str


# 页面默认查询专家的履历固定在脚本中；目标环境已有值时也会重新同步。
DEFAULT_PAGE_EXPERIENCES = (
    DemoExperience(
        scholar_id="0209a7v6",
        organization_id="colleague_tsinghua_cs",
        organization_zh="清华大学计算机科学与技术系",
        organization_en="Department of Computer Science and Technology, Tsinghua University",
        department_zh="智能计算研究室",
        department_en="Intelligent Computing Laboratory",
        position_zh="研究员",
        position_en="Researcher",
        period="2017-01 至 2024-12",
    ),
    DemoExperience(
        scholar_id="1S5195f4",
        organization_id="colleague_tsinghua_cs",
        organization_zh="清华大学计算机科学与技术系",
        organization_en="Department of Computer Science and Technology, Tsinghua University",
        department_zh="智能计算研究室",
        department_en="Intelligent Computing Laboratory",
        position_zh="副研究员",
        position_en="Associate Researcher",
        period="2018-03 至 2024-12",
    ),
)


def build_experiences(scholar_ids: list[str], cluster_size: int = 15) -> list[DemoExperience]:
    """按稳定顺序生成有关联性的履历；相同簇的时间必然重叠。"""
    if cluster_size < 2:
        raise ValueError("cluster_size 必须至少为 2")
    result: list[DemoExperience] = []
    for index, scholar_id in enumerate(scholar_ids):
        if index < len(DEFAULT_PAGE_EXPERIENCES):
            expected = DEFAULT_PAGE_EXPERIENCES[index]
            if scholar_id != expected.scholar_id:
                raise ValueError("页面默认专家必须排在生成列表前两位")
            result.append(expected)
            continue
        cluster = index // cluster_size
        org_id, org_zh, org_en = ORGANIZATIONS[cluster % len(ORGANIZATIONS)]
        dept_zh, dept_en = DEPARTMENTS[cluster % len(DEPARTMENTS)]
        pos_zh, pos_en = POSITIONS[index % len(POSITIONS)]
        start_year = 2017 + cluster % 4
        # 使同簇成员的起始月有小幅差异，但均与 2021-12 至 2024-12 重叠。
        start_month = index % cluster_size % 9 + 1
        period = f"{start_year}-{start_month:02d} 至 2024-12"
        result.append(
            DemoExperience(
                str(scholar_id),
                org_id,
                org_zh,
                org_en,
                dept_zh,
                dept_en,
                pos_zh,
                pos_en,
                period,
            )
        )
    return result


def _required_columns(session) -> set[str]:
    columns = {column["name"] for column in inspect(session.get_bind()).get_columns("dwd_scholar")}
    required = {"scholar_id", "status", *FIELDS}
    missing = required - columns
    if missing:
        raise RuntimeError(f"dwd_scholar 缺少必要字段: {', '.join(sorted(missing))}")
    return columns


def _select_rows(session, count: int) -> list[dict[str, Any]]:
    # 优先使用原本没有工作经历的活跃专家，尽量减少对既有真实数据的覆盖。
    sql = text(
        f"""
        SELECT scholar_id, {", ".join(FIELDS)}
        FROM dwd_scholar
        WHERE status = 1 AND scholar_id IS NOT NULL AND scholar_id <> ''
          AND (
            work_experience_date IS NULL OR work_experience_date = ''
            OR work_experience_institution_zh IS NULL OR work_experience_institution_zh = ''
            OR work_experience_department_zh IS NULL OR work_experience_department_zh = ''
            OR work_experience_position_zh IS NULL OR work_experience_position_zh = ''
          )
        ORDER BY scholar_id
        LIMIT :count
        """
    )
    rows = [dict(row._mapping) for row in session.execute(sql, {"count": count}).all()]
    required_sql = text(
        f"""
        SELECT scholar_id, {", ".join(FIELDS)}
        FROM dwd_scholar
        WHERE status = 1 AND scholar_id IN (:expert_a, :expert_b)
        """
    )
    required_rows = [
        dict(row._mapping)
        for row in session.execute(
            required_sql,
            {"expert_a": DEFAULT_PAGE_SCHOLAR_IDS[0], "expert_b": DEFAULT_PAGE_SCHOLAR_IDS[1]},
        ).all()
    ]
    by_id = {str(row["scholar_id"]): row for row in required_rows}
    missing = [scholar_id for scholar_id in DEFAULT_PAGE_SCHOLAR_IDS if scholar_id not in by_id]
    if missing:
        raise RuntimeError("页面默认专家在 dwd_scholar 中不存在或未启用: " + ", ".join(missing))
    selected = [by_id[scholar_id] for scholar_id in DEFAULT_PAGE_SCHOLAR_IDS]
    selected_ids = set(DEFAULT_PAGE_SCHOLAR_IDS)
    selected.extend(row for row in rows if str(row["scholar_id"]) not in selected_ids)
    return selected[:count]


def _write_plan(path: Path, experiences: list[DemoExperience], cluster_size: int) -> None:
    payload = {
        "version": 1,
        "purpose": "expert_colleague_demo",
        "generatedAt": datetime.now(UTC).isoformat(),
        "clusterSize": cluster_size,
        "pageDefaults": {
            "expertA": f"person_{DEFAULT_PAGE_SCHOLAR_IDS[0]}",
            "expertB": f"person_{DEFAULT_PAGE_SCHOLAR_IDS[1]}",
            "startTime": "2021-01",
            "endTime": "2026-08",
        },
        "experiences": [asdict(item) for item in experiences],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_plan(path: Path) -> tuple[list[DemoExperience], int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or payload.get("purpose") != "expert_colleague_demo":
        raise ValueError("数据计划格式或用途不正确")
    raw_items = payload.get("experiences")
    if not isinstance(raw_items, list):
        raise ValueError("数据计划缺少 experiences 数组")
    try:
        experiences = [DemoExperience(**item) for item in raw_items]
    except (TypeError, KeyError) as exc:
        raise ValueError(f"数据计划工作经历字段不完整: {exc}") from exc
    return experiences, int(payload.get("clusterSize") or 15)


def _validate_experiences(experiences: list[DemoExperience], expected_count: int | None) -> None:
    if expected_count is not None and len(experiences) != expected_count:
        raise ValueError(f"数据计划应包含 {expected_count} 条，实际 {len(experiences)} 条")
    if len(experiences) < 2:
        raise ValueError("数据计划至少需要两条工作经历")
    ids = [item.scholar_id for item in experiences]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        raise ValueError("数据计划存在重复 scholar_id: " + ", ".join(duplicates[:10]))
    if ids[:2] != list(DEFAULT_PAGE_SCHOLAR_IDS):
        raise ValueError("页面默认专家必须是数据计划前两条记录")
    required_text = (
        "organization_id",
        "organization_zh",
        "organization_en",
        "department_zh",
        "department_en",
        "position_zh",
        "position_en",
        "period",
    )
    for item in experiences:
        missing = [name for name in required_text if not str(getattr(item, name)).strip()]
        if missing:
            raise ValueError(f"{item.scholar_id} 存在空字段: {', '.join(missing)}")
        if len(re.findall(r"(?:19|20)\d{2}(?:-(?:0[1-9]|1[0-2]))?", item.period)) < 2:
            raise ValueError(f"{item.scholar_id} 任职时间不是有效区间: {item.period}")
    first, second = experiences[:2]
    if (first.organization_zh, first.department_zh) != (
        second.organization_zh,
        second.department_zh,
    ):
        raise ValueError("页面默认专家必须属于同一机构和部门")


def _fetch_rows_by_ids(session, scholar_ids: list[str]) -> list[dict[str, Any]]:
    sql = text(
        f"SELECT scholar_id, {', '.join(FIELDS)} FROM dwd_scholar "
        "WHERE status = 1 AND scholar_id IN :scholar_ids"
    ).bindparams(bindparam("scholar_ids", expanding=True))
    rows = [dict(row._mapping) for row in session.execute(sql, {"scholar_ids": scholar_ids}).all()]
    found = {str(row["scholar_id"]) for row in rows}
    missing = [scholar_id for scholar_id in scholar_ids if scholar_id not in found]
    if missing:
        raise RuntimeError(
            f"数据计划中有 {len(missing)} 个专家在 dwd_scholar 中不存在或未启用: "
            + ", ".join(missing[:20])
        )
    by_id = {str(row["scholar_id"]): row for row in rows}
    return [by_id[scholar_id] for scholar_id in scholar_ids]


def _update_mysql(session, experiences: list[DemoExperience]) -> int:
    sql = text(
        """
        UPDATE dwd_scholar SET
          scholar_org_name_zh=:organization_zh,
          scholar_org_name_en=:organization_en,
          work_experience_date=:period,
          work_experience_institution_zh=:organization_zh,
          work_experience_institution_en=:organization_en,
          work_experience_department_zh=:department_zh,
          work_experience_department_en=:department_en,
          work_experience_position_zh=:position_zh,
          work_experience_position_en=:position_en,
          update_time=CURRENT_TIMESTAMP
        WHERE scholar_id=:scholar_id AND status=1
        """
    )
    session.execute(sql, [asdict(item) for item in experiences])
    return len(experiences)


def _write_graph(experiences: list[DemoExperience], batch_id: str) -> dict[str, int | str]:
    # 固定写 dev；机构和专家节点必须已存在，只幂等创建/更新任职边并补充属性。
    settings = TRSGraphSettings.from_env().model_copy(update={"space": "dev"})
    graph = TRSGraphClient(settings)
    graph.connect()
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    try:
        candidates: list[tuple[DemoExperience, str, str, list[Any]]] = []
        skipped_missing_node = 0
        for item in experiences:
            person_id = person_vid(item.scholar_id)
            target_id = f"org_{item.organization_id}"
            try:
                all_edges = graph.get_node_edges(
                    person_id, direction="out", edge_type="AFFILIATED_WITH", limit=100
                )
            except Exception as exc:
                if item.scholar_id in DEFAULT_PAGE_SCHOLAR_IDS:
                    raise
                skipped_missing_node += 1
                logger.warning("跳过任职边读取异常 %s: %s", person_id, exc)
                continue
            edges = [edge for edge in all_edges if str(edge.target_id) == target_id]
            candidates.append((item, person_id, target_id, edges))

        updated_edges = 0
        created_edges = 0
        updated_persons = 0
        for item, person_id, target_id, edges in candidates:
            try:
                graph.update_node(
                    person_id,
                    {
                        "scholar_org": item.organization_zh,
                        "work_experience_date": item.period,
                        "work_experience_institution_en": item.organization_en,
                        "work_experience_department_en": item.department_en,
                        "work_experience_position_en": item.position_en,
                        "work_experience_institution_zh": item.organization_zh,
                        "work_experience_department_zh": item.department_zh,
                        "work_experience_position_zh": item.position_zh,
                        "ingest_batch": batch_id,
                        "ingest_time": now,
                    },
                )
                updated_persons += 1
            except Exception as exc:
                skipped_missing_node += 1
                logger.warning("跳过专家节点属性更新 %s: %s", person_id, exc)
                continue

            props = {
                "affiliation_name": item.organization_zh,
                "source": "scholar",
                "source_table": "dwd_scholar",
                "source_record_id": item.scholar_id,
                "ingest_batch": batch_id,
                "ingest_time": now,
                "work_experience_date": item.period,
                "work_experience_department_zh": item.department_zh,
                "work_experience_position_zh": item.position_zh,
                **organization_provenance("dwd_scholar", item.organization_id),
                **confidence_props(
                    CONFIDENCE_SOURCE_PRIMARY_KEY,
                    "demo_existing_org_id",
                    "演示计划使用 dev 图空间中已存在的 Organization ID",
                ),
            }
            graph.merge_edge(
                person_id,
                target_id,
                "AFFILIATED_WITH",
                {"source_record_id": item.scholar_id},
                props,
            )
            if edges:
                updated_edges += 1
            else:
                created_edges += 1
        return {
            "space": "dev",
            "updatedPersons": updated_persons,
            "updatedAffiliations": updated_edges,
            "createdNodes": 0,
            "createdEdges": created_edges,
            "skippedMissingNode": skipped_missing_node,
            "skippedMissingAffiliation": 0,
        }
    finally:
        graph.close()


def _backup(rows: list[dict[str, Any]], path: Path) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def run(
    *,
    count: int,
    cluster_size: int,
    database: str,
    write: bool,
    backup_file: Path | None,
    plan_file: Path | None = None,
    export_plan: Path | None = None,
    mysql_only: bool = False,
    graph_only: bool = False,
) -> dict[str, Any]:
    if count < 2:
        raise ValueError("count 必须至少为 2")
    if mysql_only and graph_only:
        raise ValueError("--mysql-only 与 --graph-only 不能同时使用")
    if export_plan is not None and plan_file is not None:
        raise ValueError("--export-plan 不能与 --plan-file 同时使用")

    mysql = MySQLClient(database=database)
    session = mysql.session()
    try:
        _required_columns(session)
        if plan_file is not None:
            experiences, plan_cluster_size = _load_plan(plan_file)
            _validate_experiences(experiences, count)
            rows = _fetch_rows_by_ids(session, [item.scholar_id for item in experiences])
            cluster_size = plan_cluster_size
            plan_source = str(plan_file.resolve())
        else:
            rows = _select_rows(session, count)
            if len(rows) < count:
                raise RuntimeError(f"仅找到 {len(rows)} 条有效学者，不足请求的 {count} 条")
            experiences = build_experiences([str(row["scholar_id"]) for row in rows], cluster_size)
            _validate_experiences(experiences, count)
            plan_source = "generated-preview"

        if export_plan is not None:
            _write_plan(export_plan, experiences, cluster_size)
            return {
                "mode": "export-plan",
                "planFile": str(export_plan.resolve()),
                "selected": len(experiences),
                "clusters": (len(experiences) + cluster_size - 1) // cluster_size,
            }

        result: dict[str, Any] = {
            "mode": "write" if write else "dry-run",
            "mysqlDatabase": database,
            "graphSpace": os.environ.get("TRS_GRAPH_SPACE", "dev"),
            "planSource": plan_source,
            "selected": len(experiences),
            "clusters": (len(experiences) + cluster_size - 1) // cluster_size,
            "pageDefaults": {
                "expertA": f"person_{DEFAULT_PAGE_SCHOLAR_IDS[0]}",
                "expertB": f"person_{DEFAULT_PAGE_SCHOLAR_IDS[1]}",
                "startTime": "2021-01",
                "endTime": "2026-08",
                "included": [item.scholar_id for item in experiences[:2]]
                == list(DEFAULT_PAGE_SCHOLAR_IDS),
            },
            "preview": [asdict(item) for item in experiences[:5]],
        }
        if not write:
            return result

        batch_id = f"BATCH_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_colleague_demo"
        if not graph_only:
            target = backup_file or Path.cwd() / f"{batch_id}_mysql_backup.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            _backup(rows, target)
            update_result = _update_mysql(session, experiences)
            session.commit()
            result["backupFile"] = str(target.resolve())
            result["mysqlUpdated"] = update_result
        if not mysql_only:
            result["graph"] = _write_graph(experiences, batch_id)
        result["batch"] = batch_id
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        mysql.dispose()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=300, help="学者数，默认 300")
    parser.add_argument(
        "--cluster-size", type=int, default=15, help="每个同事关系簇的人数，默认 15"
    )
    parser.add_argument("--database", default=os.environ.get("MYSQL_DATABASE", "gkx_element"))
    parser.add_argument("--backup-file", type=Path, help="写入前 MySQL 原值 JSON 快照路径")
    parser.add_argument("--export-plan", type=Path, help="从数据库选择专家并导出固定 JSON 数据计划")
    parser.add_argument("--plan-file", type=Path, help="读取已审核的固定 JSON 数据计划")
    parser.add_argument("--mysql-only", action="store_true", help="只更新 MySQL，不写图")
    parser.add_argument(
        "--graph-only", action="store_true", help="只在 dev 幂等创建/更新任职边及属性"
    )
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写 MySQL 和图空间")
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    args = _parse_args()
    print(
        json.dumps(
            run(
                count=args.count,
                cluster_size=args.cluster_size,
                database=args.database,
                write=not args.dry_run,
                backup_file=args.backup_file,
                plan_file=args.plan_file,
                export_plan=args.export_plan,
                mysql_only=args.mysql_only,
                graph_only=args.graph_only,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
