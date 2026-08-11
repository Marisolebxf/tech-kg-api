"""任务中心、人工审核与工作流定义的轻量持久化仓库。"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class WorkflowRepository:
    """使用 SQLite 保存控制面数据，避免页面状态随进程重启丢失。"""

    def __init__(self, database_path: str | None = None) -> None:
        backend_dir = Path(__file__).resolve().parents[1]
        default_path = (
            Path(os.getenv("TECH_KG_STATE_DIR", str(backend_dir / "var"))) / "tech-kg-workflows.db"
        )
        self.database_path = database_path or os.getenv("WORKFLOW_DATABASE_PATH", str(default_path))
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS batches (
                    id TEXT PRIMARY KEY, update_date TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, stage TEXT NOT NULL,
                    task_status TEXT NOT NULL, domain TEXT NOT NULL, kind TEXT NOT NULL,
                    processed_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    id TEXT PRIMARY KEY, task_id TEXT NOT NULL, batch_id TEXT NOT NULL,
                    status TEXT NOT NULL, domain TEXT NOT NULL, category TEXT NOT NULL,
                    updated_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS source_updates (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, domain TEXT NOT NULL,
                    detected_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflow_definitions (
                    id TEXT PRIMARY KEY, workflow_type TEXT NOT NULL UNIQUE,
                    category TEXT NOT NULL, active INTEGER NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflow_executions (
                    id TEXT PRIMARY KEY, definition_id TEXT NOT NULL, workflow_id TEXT NOT NULL,
                    run_id TEXT, status TEXT NOT NULL, started_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflow_schedules (
                    id TEXT PRIMARY KEY, definition_id TEXT NOT NULL, active INTEGER NOT NULL,
                    payload TEXT NOT NULL
                );
                """
            )
            self._remove_workflow_type_unique_constraint(connection)
            count = connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            if count == 0:
                self._seed(connection)

    @staticmethod
    def _remove_workflow_type_unique_constraint(connection: sqlite3.Connection) -> None:
        indexes = connection.execute("PRAGMA index_list(workflow_definitions)").fetchall()
        has_legacy_unique = False
        for index in indexes:
            if not index[2]:
                continue
            columns = connection.execute(f"PRAGMA index_info({index[1]})").fetchall()
            if [column[2] for column in columns] == ["workflow_type"]:
                has_legacy_unique = True
                break
        if not has_legacy_unique:
            return
        connection.executescript(
            """
            ALTER TABLE workflow_definitions RENAME TO workflow_definitions_legacy;
            CREATE TABLE workflow_definitions (
                id TEXT PRIMARY KEY, workflow_type TEXT NOT NULL,
                category TEXT NOT NULL, active INTEGER NOT NULL, payload TEXT NOT NULL
            );
            INSERT OR REPLACE INTO workflow_definitions
                (id, workflow_type, category, active, payload)
            SELECT id, workflow_type, category, active, payload
            FROM workflow_definitions_legacy;
            DROP TABLE workflow_definitions_legacy;
            """
        )

    def _seed(self, connection: sqlite3.Connection) -> None:
        batches = [
            {
                "id": "UPD-20260714",
                "name": "2026-07-14 数据更新",
                "updateDate": "2026-07-14",
                "dataWindow": "2026-07-13 02:00—2026-07-14 02:00",
                "source": "科技要素数据库",
                "trigger": "每日定时更新",
                "input": 25140,
                "entities": 8426,
                "relations": 35620,
                "completed": 43335,
                "abnormal": 711,
                "progress": 99,
                "status": "待审核",
                "startedAt": "2026-07-14 02:00:00",
                "completedAt": "等待人工处理完成",
            },
            {
                "id": "UPD-20260713",
                "name": "2026-07-13 数据更新",
                "updateDate": "2026-07-13",
                "dataWindow": "2026-07-12 02:00—2026-07-13 02:00",
                "source": "科技要素数据库",
                "trigger": "每日定时更新",
                "input": 23876,
                "entities": 7981,
                "relations": 32450,
                "completed": 40431,
                "abnormal": 42,
                "progress": 100,
                "status": "已完成",
                "startedAt": "2026-07-13 02:00:00",
                "completedAt": "2026-07-13 02:36:42",
            },
        ]
        for batch in batches:
            connection.execute(
                "INSERT INTO batches(id, update_date, payload) VALUES (?, ?, ?)",
                (batch["id"], batch["updateDate"], _json(batch)),
            )

        tasks = self._seed_tasks()
        for task in tasks:
            connection.execute(
                """INSERT INTO tasks(id, batch_id, stage, task_status, domain, kind,
                   processed_at, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task["id"],
                    task["batchId"],
                    task["stage"],
                    task["taskStatus"],
                    task["dataDomain"],
                    task["kind"],
                    task["processedAt"],
                    _json(task),
                ),
            )

        reviews = self._seed_reviews()
        for review in reviews:
            connection.execute(
                """INSERT INTO reviews(id, task_id, batch_id, status, domain, category,
                   updated_at, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    review["id"],
                    review["id"],
                    review["batch"],
                    review["status"],
                    review["domain"],
                    review["category"],
                    review["updatedAt"],
                    _json(review),
                ),
            )

        updates = [
            {
                "change": "新增",
                "type": "论文",
                "domain": "论文",
                "id": "P202607140018",
                "content": "《多模态大模型知识推理方法研究》",
                "time": "02:00:13",
                "detectedAt": "2026-07-14 02:00:13",
                "source": "dwd_zh_paper_detail",
                "field": "整条记录",
                "before": "不存在",
                "after": "新增论文标题、作者、机构、关键词和 DOI 信息",
                "result": "已进入数据清洗与论文实体对齐",
            },
            {
                "change": "新增",
                "type": "专家",
                "domain": "人才",
                "id": "EXPERT_20418",
                "content": "周启航 · 中国科学院自动化研究所",
                "time": "02:00:18",
                "detectedAt": "2026-07-14 02:00:18",
                "source": "dwd_scholar",
                "field": "整条记录",
                "before": "不存在",
                "after": "新增专家姓名、任职机构与研究方向",
                "result": "已进入专家候选实体对齐",
            },
            {
                "change": "修改",
                "type": "专利",
                "domain": "专利",
                "id": "CN2026102841",
                "content": "法律状态：公开 → 实质审查",
                "time": "02:00:22",
                "detectedAt": "2026-07-14 02:00:22",
                "source": "dwd_patent",
                "field": "legal_status",
                "before": "公开",
                "after": "实质审查",
                "result": "已更新专利属性，等待增量图谱入库",
            },
            {
                "change": "删除",
                "type": "项目",
                "domain": "项目",
                "id": "PROJ_2024_0892",
                "content": "来源记录已标记删除，图谱对象待下线",
                "time": "02:00:31",
                "detectedAt": "2026-07-14 02:00:31",
                "source": "dwd_zh_project",
                "field": "is_deleted",
                "before": "0",
                "after": "1",
                "result": "已进入删除影响分析，确认关系依赖后下线",
            },
        ]
        for item in updates:
            connection.execute(
                "INSERT INTO source_updates(domain, detected_at, payload) VALUES (?, ?, ?)",
                (item["domain"], item["detectedAt"], _json(item)),
            )

        policy = {
            "id": "auto-graph-build",
            "enabled": True,
            "frequency": "每天",
            "executionTime": "02:00",
            "timezone": "Asia/Shanghai",
            "cron": "0 2 * * *",
            "nextRunAt": "2026-07-15 02:00:00",
            "skipWhenNoChanges": True,
        }
        connection.execute(
            "INSERT INTO settings(key, payload) VALUES ('update_policy', ?)", (_json(policy),)
        )

        definitions = [
            ("entity-paper", "kg.entity.paper", "entity", "论文实体工作流"),
            ("entity-scholar", "kg.entity.scholar", "entity", "人才实体工作流"),
            ("entity-patent", "kg.entity.patent", "entity", "专利实体工作流"),
            ("entity-organization", "kg.entity.organization", "entity", "机构实体工作流"),
            ("relation-authorship", "kg.relation.authorship", "relation", "论文作者关系工作流"),
            ("relation-employment", "kg.relation.employment", "relation", "人才任职关系工作流"),
            ("relation-citation", "kg.relation.citation", "relation", "论文引用关系工作流"),
            ("relation-cooperation", "kg.relation.cooperation", "relation", "合作关系工作流"),
            ("graph-build", "kg.graph.build", "graph", "图谱构建总工作流"),
        ]
        for definition_id, workflow_type, category, name in definitions:
            payload = {
                "id": definition_id,
                "name": name,
                "workflowType": workflow_type,
                "category": category,
                "taskQueue": os.getenv("TEMPORAL_TASK_QUEUE", "tech-kg-workflows"),
                "active": True,
                "sourceKind": "builtin",
                "steps": ["读取增量", "标准化", "抽取/对齐", "质量校验", "图谱写入"],
                "createdAt": _now(),
            }
            connection.execute(
                """INSERT INTO workflow_definitions(id, workflow_type, category, active, payload)
                   VALUES (?, ?, ?, 1, ?)""",
                (definition_id, workflow_type, category, _json(payload)),
            )

    @staticmethod
    def _steps(blocking: str | None = None) -> list[dict[str, Any]]:
        raw = [
            ("source", "数据接入", "数据处理", "读取业务域增量数据"),
            ("normalize", "清洗标准化", "数据处理", "执行字段、枚举和字典标准化"),
            ("schema", "Schema 映射", "图谱构建", "映射实体、关系与属性 Schema"),
            ("extract", "实体关系抽取", "图谱构建", "运行领域专属实体/关系工作流"),
            ("validate", "质量校验", "图谱构建", "执行置信度、证据与唯一性校验"),
            ("persist", "图谱入库", "图谱构建", "幂等写入实体、关系和属性"),
        ]
        result = []
        blocked = False
        for step_id, name, phase, description in raw:
            if blocked:
                status = "待执行"
            elif step_id == blocking:
                status = "需人工处理"
                blocked = True
            else:
                status = "成功"
            result.append(
                {
                    "id": step_id,
                    "name": name,
                    "phase": phase,
                    "description": description,
                    "status": status,
                    "count": "1 个处理对象",
                    "abnormal": "1" if status == "需人工处理" else "0",
                    "duration": "未完成" if status != "成功" else "6秒",
                }
            )
        return result

    @classmethod
    def _seed_tasks(cls) -> list[dict[str, Any]]:
        base = [
            (
                "PI-20260714-0101",
                "图谱构建",
                "实体",
                "论文",
                "大模型抽取批次",
                "流程实例",
                "批量实体关系抽取",
                "论文成果批次",
                "模型批量输出异常",
                "执行出错",
                "extract",
                "",
            ),
            (
                "PI-20260714-0102",
                "图谱构建",
                "属性",
                "企业",
                "Schema 映射批次",
                "流程实例",
                "批量 Schema 映射",
                "企业基本信息表",
                "Schema 批量映射失败",
                "执行出错",
                "schema",
                "",
            ),
            (
                "PI-20260714-0103",
                "数据处理",
                "属性",
                "专利",
                "专利状态标准化批次",
                "流程实例",
                "公共字典标准化",
                "专利基本信息表",
                "公共字典配置异常",
                "执行出错",
                "normalize",
                "",
            ),
            (
                "PI-20260714-0104",
                "图谱构建",
                "实体",
                "人才",
                "李晓峰 / Li Xiaofeng",
                "候选专家实体",
                "实体对齐",
                "专家基本信息表",
                "单任务执行失败",
                "执行出错",
                "extract",
                "",
            ),
            (
                "PI-20260714-0001",
                "图谱构建",
                "实体",
                "人才",
                "张明远",
                "科技专家",
                "新增实体",
                "专家基本信息表",
                "",
                "执行完成",
                None,
                "0.94",
            ),
            (
                "PI-20260714-0003",
                "图谱构建",
                "关系",
                "论文",
                "数字抽象 → 矩阵分析",
                "主题相近",
                "新增关系",
                "实体主题关联表",
                "低置信度",
                "等待人工审核",
                "validate",
                "0.72",
            ),
            (
                "PI-20260714-0004",
                "图谱构建",
                "实体",
                "人才",
                "张明远 / Zhang Mingyuan",
                "候选专家实体",
                "实体合并",
                "专家基本信息表",
                "实体冲突",
                "等待人工审核",
                "validate",
                "0.82",
            ),
            (
                "PI-20260714-0005",
                "图谱构建",
                "关系",
                "企业",
                "华南智能芯片 → 腾讯",
                "企业合作",
                "新增关系",
                "企业合作记录表",
                "关系证据不足",
                "等待人工审核",
                "validate",
                "0.74",
            ),
            (
                "PI-20260714-0007",
                "数据处理",
                "实体",
                "论文",
                "重复论文成果记录",
                "论文成果",
                "记录去重",
                "论文成果表",
                "唯一性冲突",
                "等待人工审核",
                "validate",
                "0.69",
            ),
            (
                "PI-20260714-0010",
                "数据处理",
                "属性",
                "论文",
                "论文标题缺失",
                "论文成果",
                "属性补全",
                "论文成果表",
                "必填缺失",
                "执行完成",
                None,
                "0.93",
            ),
            (
                "PI-20260713-0008",
                "图谱构建",
                "实体",
                "专利",
                "陈卓 / Chen Zhuo",
                "科技专家",
                "实体合并",
                "专家基本信息表",
                "低置信度",
                "执行完成",
                None,
                "0.72",
            ),
        ]
        result = []
        for index, row in enumerate(base):
            (
                task_id,
                stage,
                kind,
                domain,
                object_name,
                object_type,
                action,
                source_table,
                review_type,
                status,
                blocking,
                confidence,
            ) = row
            batch_id = "UPD-20260713" if "20260713" in task_id else "UPD-20260714"
            result.append(
                {
                    "id": task_id,
                    "batchId": batch_id,
                    "stage": stage,
                    "kind": kind,
                    "objectId": task_id.replace("PI-", "OBJ-"),
                    "objectName": object_name,
                    "objectType": object_type,
                    "action": action,
                    "sourceTable": source_table,
                    "sourceRecordId": task_id.replace("PI-", "SRC-"),
                    "rule": review_type or "领域图谱质量规则",
                    "confidence": confidence,
                    "result": "等待人工确认" if blocking else "任务已完成并产生可验收结果",
                    "status": "待人工处理" if status == "等待人工审核" else "已完成",
                    "taskStatus": status,
                    "dataDomain": f"{domain}域"
                    if domain not in {"企业", "专利"}
                    else f"{domain}域",
                    "processedAt": f"2026-07-{13 if batch_id.endswith('13') else 14} 10:{8 + index:02d}:00",
                    "reviewType": review_type or None,
                    "currentStep": next(
                        (
                            item["name"]
                            for item in cls._steps(blocking)
                            if item["id"] == (blocking or "persist")
                        ),
                        "图谱入库",
                    ),
                    "steps": cls._steps(blocking),
                    "workflowType": "kg.graph.build",
                    "workflowId": f"wf-{task_id.lower()}",
                    "runId": None,
                    "input": {"batchId": batch_id, "domain": domain},
                    "output": {"object": object_name, "confidence": confidence},
                    "logs": [
                        f"{task_id} INFO 开始执行 {stage} 工作流",
                        f"{task_id} {'WARN 等待人工处理' if blocking else 'INFO 执行完成'}",
                    ],
                }
            )
        return result

    @staticmethod
    def _seed_reviews() -> list[dict[str, Any]]:
        rows = [
            (
                "PI-20260714-0101",
                "大模型输出格式错误",
                "论文",
                "论文记录",
                "《多模态大模型知识推理方法研究》",
                "LLM-SCHEMA-FAIL-001",
                "模型返回字段无法解析为目标 JSON Schema",
                "",
                "张建图",
                "大模型抽取",
                "论文成果表",
                "P202607140326",
                "抽取流程异常",
            ),
            (
                "PI-20260714-0102",
                "Schema 字段映射失败",
                "企业",
                "企业记录",
                "华南智能芯片有限公司",
                "SCHEMA-MAP-FAIL-006",
                "来源字段无法映射到 Organization.org_category",
                "",
                "张建图",
                "Schema 映射",
                "企业基本信息表",
                "ORG_4403018892",
                "Schema 映射",
            ),
            (
                "PI-20260714-0103",
                "专利状态标准化失败",
                "专利",
                "专利记录",
                "《一种智能芯片封装方法》",
                "DICT-CONFIG-FAIL-003",
                "原始状态未命中当前专利状态字典",
                "",
                "李质量",
                "清洗标准化",
                "专利基本信息表",
                "CN2026101843",
                "标准化/枚举",
            ),
            (
                "PI-20260714-0104",
                "实体抽取超时",
                "人才",
                "专家记录",
                "李晓峰 / Li Xiaofeng",
                "ENTITY-RUNTIME-004",
                "实体抽取服务超过 30 秒未返回结果",
                "",
                "王审核",
                "实体抽取",
                "专家基本信息表",
                "EXPERT-20566",
                "抽取流程异常",
            ),
            (
                "PI-20260714-0003",
                "关系类型置信度不足",
                "论文",
                "论文引用关系",
                "《数字抽象方法研究》 → 《矩阵分析基础》",
                "REL-CONFIDENCE-003",
                "主题共现与两跳路径证据不足以自动入图",
                "0.72",
                "王审核",
                "关系校验",
                "实体主题关联表",
                "TOPIC-DIGITAL-040",
                "结果低于阈值",
            ),
            (
                "PI-20260714-0004",
                "实体类型判断错误",
                "人才",
                "专家实体",
                "张明远 / Zhang Mingyuan",
                "ALIGN-ENTITY-017",
                "源记录应归类为专家，系统映射为人才",
                "0.82",
                "王审核",
                "Schema 实体分类",
                "专家基本信息表",
                "EXPERT-20418",
                "结果低于阈值",
            ),
            (
                "PI-20260714-0005",
                "合作关系证据不足",
                "企业",
                "企业合作关系",
                "华南智能芯片有限公司 → 腾讯科技有限公司",
                "REL-EVIDENCE-009",
                "仅命中 1 个来源，未达到双来源入库条件",
                "0.74",
                "陈治理",
                "关系证据校验",
                "企业合作记录表",
                "COOP-89321-A",
                "结果低于阈值",
            ),
            (
                "PI-20260714-0007",
                "论文唯一性冲突",
                "论文",
                "论文源记录",
                "《多源科技数据融合方法研究》",
                "DQ-UNIQUE-003",
                "同一 paper_id 对应 3 条来源记录",
                "0.69",
                "李质量",
                "唯一性校验",
                "论文成果表",
                "P202607130089",
                "数据质量",
            ),
            (
                "PI-20260714-0010",
                "论文标题缺失",
                "论文",
                "论文源记录",
                "《知识图谱增量构建方法研究》",
                "DQ-REQUIRED-001",
                "原始标题为空，DOI 可匹配可信成果",
                "0.93",
                "李质量",
                "必填校验",
                "论文成果表",
                "P202607130068",
                "数据质量",
            ),
            (
                "PI-20260713-0008",
                "专家实体置信度不足",
                "专利",
                "专利发明人实体",
                "陈卓 / Chen Zhuo",
                "ALIGN-CONFIDENCE-003",
                "机构别名经人工确认后完成合并",
                "0.72",
                "陈治理",
                "实体结果校验",
                "专家基本信息表",
                "EXPERT-19882",
                "结果低于阈值",
            ),
        ]
        completed = {"PI-20260714-0010", "PI-20260713-0008"}
        result = []
        for index, row in enumerate(rows):
            (
                item_id,
                review_type,
                domain,
                object_type,
                obj,
                rule_id,
                evidence,
                score,
                handler,
                node,
                source_table,
                source_record_id,
                category,
            ) = row
            status = "已完成" if item_id in completed else "待处理"
            result.append(
                {
                    "id": item_id,
                    "batch": "UPD-20260713" if "20260713" in item_id else "UPD-20260714",
                    "module": "数据处理"
                    if review_type in {"论文唯一性冲突", "论文标题缺失", "专利状态标准化失败"}
                    else "图谱构建",
                    "node": node,
                    "type": review_type,
                    "category": category,
                    "domain": domain,
                    "objectType": object_type,
                    "objectId": item_id.replace("PI-", "OBJ-"),
                    "object": obj,
                    "ruleId": rule_id,
                    "evidence": evidence,
                    "score": score,
                    "handler": handler,
                    "status": status,
                    "updatedAt": f"07-14 10:{8 + index:02d}",
                    "sourceResult": "异常结果已隔离，未进入生产图谱",
                    "suggestion": "人工修正后从当前节点重跑",
                    "sourceTable": source_table,
                    "sourceRecordId": source_record_id,
                    "decision": "修正后重跑并通过" if status == "已完成" else None,
                    "decisionNote": "已人工核验并完成重跑。" if status == "已完成" else None,
                    "completedAt": "2026-07-14 10:21:47" if status == "已完成" else None,
                    "flow": WorkflowRepository._steps("validate"),
                    "revision": 1,
                }
            )
        return result

    @staticmethod
    def _rows(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
        return [json.loads(row["payload"]) for row in rows]

    def list_batches(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return self._rows(
                connection.execute("SELECT payload FROM batches ORDER BY update_date DESC")
            )

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM batches WHERE id = ?", (batch_id,)
            ).fetchone()
            return json.loads(row["payload"]) if row else None

    def list_tasks(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        clauses, params = [], []
        mapping = {
            "stage": "stage",
            "task_status": "task_status",
            "domain": "domain",
            "kind": "kind",
            "batch_id": "batch_id",
        }
        for key, column in mapping.items():
            value = filters.get(key)
            if value:
                clauses.append(f"{column} = ?")
                params.append(value)
        if filters.get("start_time"):
            clauses.append("processed_at >= ?")
            params.append(filters["start_time"])
        if filters.get("end_time"):
            clauses.append("processed_at <= ?")
            params.append(filters["end_time"])
        sql = "SELECT payload FROM tasks"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY processed_at DESC"
        with self._connect() as connection:
            items = self._rows(connection.execute(sql, params))
        keyword = filters.get("keyword")
        if keyword:
            items = [item for item in items if keyword.lower() in _json(item).lower()]
        return items

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            return json.loads(row["payload"]) if row else None

    def save_task(self, task: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO tasks(id, batch_id, stage, task_status, domain, kind,
                   processed_at, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task["id"],
                    task["batchId"],
                    task["stage"],
                    task["taskStatus"],
                    task["dataDomain"],
                    task["kind"],
                    task["processedAt"],
                    _json(task),
                ),
            )

    def list_reviews(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        clauses, params = [], []
        mapping = {
            "status": "status",
            "domain": "domain",
            "category": "category",
            "batch_id": "batch_id",
        }
        for key, column in mapping.items():
            value = filters.get(key)
            if value:
                clauses.append(f"{column} = ?")
                params.append(value)
        if filters.get("start_time"):
            clauses.append("updated_at >= ?")
            params.append(filters["start_time"])
        if filters.get("end_time"):
            clauses.append("updated_at <= ?")
            params.append(filters["end_time"])
        sql = "SELECT payload FROM reviews"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at DESC"
        with self._connect() as connection:
            items = self._rows(connection.execute(sql, params))
        keyword = filters.get("keyword")
        if keyword:
            items = [item for item in items if keyword.lower() in _json(item).lower()]
        return items

    def get_review(self, review_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM reviews WHERE id = ?", (review_id,)
            ).fetchone()
            return json.loads(row["payload"]) if row else None

    def save_review(self, review: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO reviews(id, task_id, batch_id, status, domain, category,
                   updated_at, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    review["id"],
                    review["id"],
                    review["batch"],
                    review["status"],
                    review["domain"],
                    review["category"],
                    review["updatedAt"],
                    _json(review),
                ),
            )

    def list_source_updates(
        self, domain: str | None, since: str | None, until: str | None
    ) -> list[dict[str, Any]]:
        clauses, params = [], []
        if domain:
            clauses.append("domain = ?")
            params.append(domain)
        if since:
            clauses.append("detected_at >= ?")
            params.append(since)
        if until:
            clauses.append("detected_at <= ?")
            params.append(until)
        sql = "SELECT payload FROM source_updates"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY detected_at DESC"
        with self._connect() as connection:
            return self._rows(connection.execute(sql, params))

    def get_setting(self, key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM settings WHERE key = ?", (key,)
            ).fetchone()
            return json.loads(row["payload"]) if row else None

    def save_setting(self, key: str, payload: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO settings(key, payload) VALUES (?, ?)", (key, _json(payload))
            )

    def list_definitions(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return self._rows(
                connection.execute("SELECT payload FROM workflow_definitions ORDER BY category, id")
            )

    def get_definition(self, definition_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM workflow_definitions WHERE id = ?", (definition_id,)
            ).fetchone()
            return json.loads(row["payload"]) if row else None

    def save_definition(self, definition: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO workflow_definitions(id, workflow_type, category, active, payload)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    definition["id"],
                    definition["workflowType"],
                    definition["category"],
                    int(definition.get("active", True)),
                    _json(definition),
                ),
            )

    def save_execution(self, execution: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO workflow_executions(id, definition_id, workflow_id,
                   run_id, status, started_at, payload) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    execution["id"],
                    execution["definitionId"],
                    execution["workflowId"],
                    execution.get("runId"),
                    execution["status"],
                    execution["startedAt"],
                    _json(execution),
                ),
            )

    def get_execution(self, execution_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM workflow_executions WHERE id = ?", (execution_id,)
            ).fetchone()
            return json.loads(row["payload"]) if row else None

    def save_schedule(self, schedule: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO workflow_schedules(id, definition_id, active, payload)
                   VALUES (?, ?, ?, ?)""",
                (
                    schedule["id"],
                    schedule["definitionId"],
                    int(schedule.get("active", True)),
                    _json(schedule),
                ),
            )

    def list_schedules(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return self._rows(
                connection.execute("SELECT payload FROM workflow_schedules ORDER BY id")
            )

    def get_schedule(self, schedule_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM workflow_schedules WHERE id = ?", (schedule_id,)
            ).fetchone()
            return json.loads(row["payload"]) if row else None

    def delete_schedule(self, schedule_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM workflow_schedules WHERE id = ?", (schedule_id,)
            )
            return cursor.rowcount > 0

    def source_health(self) -> list[dict[str, Any]]:
        now = datetime.now(UTC).astimezone()
        return [
            {
                "id": "mysql-elements",
                "name": "科技要素数据库",
                "type": "MySQL",
                "domain": "综合",
                "status": "健康",
                "latencyMs": 18,
                "lastCheckedAt": now.strftime("%Y-%m-%d %H:%M:%S"),
                "message": "连接与增量游标正常",
            },
            {
                "id": "trs-graph",
                "name": "图数据库服务",
                "type": "NebulaGraph",
                "domain": "图谱",
                "status": "健康",
                "latencyMs": 32,
                "lastCheckedAt": now.strftime("%Y-%m-%d %H:%M:%S"),
                "message": "读写探针正常",
            },
            {
                "id": "temporal",
                "name": "Temporal",
                "type": "Workflow",
                "domain": "调度",
                "status": "待探测",
                "latencyMs": None,
                "lastCheckedAt": now.strftime("%Y-%m-%d %H:%M:%S"),
                "message": "调用 /workflow-system/health 获取实时状态",
            },
        ]

    def reset_for_tests(self) -> None:
        with self._lock:
            Path(self.database_path).unlink(missing_ok=True)
            self._initialize()


repository = WorkflowRepository()
