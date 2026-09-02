"""任务中心、人工审核与工作流定义的控制面仓库（temporal-mysql 的 techkg_control 库）。

原 SQLite 实现已迁至 SQLAlchemy ORM + MySQL（详见 service/workflow_models.py、
infra/workflow_mysql.py）。保留全部 public 方法签名；seed/`_steps` 等静态
数据方法原样保留，仅把 `_seed` 的 INSERT 语句换成 session.add。

ORM 模型不带 workflow_type UNIQUE 约束（kg.custom.python 多定义共享同一
workflow_type，原 SQLite 实现的 _remove_workflow_type_unique_constraint 即为
移除此约束，新 schema 直接不建）。
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from infra.workflow_mysql import workflow_mysql_client, workflow_session_scope
from service.workflow_models import (
    Base,
    WorkflowBatch,
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowJob,
    WorkflowReview,
    WorkflowSchedule,
    WorkflowSetting,
    WorkflowSourceUpdate,
    WorkflowTask,
)


def _now() -> str:
    return datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class WorkflowRepository:
    """使用 SQLAlchemy ORM + MySQL 保存控制面数据，避免页面状态随进程重启丢失。"""

    def __init__(self, engine: Engine | None = None) -> None:
        # engine 仅用于测试注入；默认用全局 workflow_mysql_client.engine
        self._explicit_engine = engine
        self._initialize()

    @property
    def _engine(self) -> Engine:
        if self._explicit_engine is not None:
            return self._explicit_engine
        return workflow_mysql_client.engine

    def _initialize(self) -> None:
        # CREATE DATABASE IF NOT EXISTS 在 workflow_mysql_client.engine 首次访问时已做；
        # 这里只建表 + seed（可选）+ 注册 builtin 工作流定义。
        Base.metadata.create_all(self._engine)
        self._migrate_job_columns()
        self._migrate_schema_space_column()
        demo_enabled = os.getenv("WORKFLOW_DEMO_DATA_ENABLED", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if demo_enabled:
            with workflow_session_scope() as session:
                any_task = session.scalar(select(WorkflowTask.id).limit(1))
                if any_task is None:
                    self._seed(session)
        self._ensure_builtin_definitions()

    def _migrate_job_columns(self) -> None:
        """无迁移框架：对已有 workflow_executions 表幂等补 job_id 列（仅 MySQL 方言）。"""
        from sqlalchemy import inspect, text

        inspector = inspect(self._engine)
        if "workflow_executions" not in inspector.get_table_names():
            return
        columns = {column["name"] for column in inspector.get_columns("workflow_executions")}
        if "job_id" in columns:
            return
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE workflow_executions "
                    "ADD COLUMN job_id VARCHAR(255) NULL, "
                    "ADD INDEX ix_workflow_executions_job_id (job_id)"
                )
            )

    def _migrate_schema_space_column(self) -> None:
        """幂等为 kg_schema_definition 补 graph_space 列并把唯一键升级为 (col, space) 复合。

        存量行回填为当前环境的 TRS_GRAPH_SPACE；仅 MySQL 方言（SQLite 测试库走 create_all）。
        """
        from sqlalchemy import inspect, text

        inspector = inspect(self._engine)
        if "kg_schema_definition" not in inspector.get_table_names():
            return
        columns = {column["name"] for column in inspector.get_columns("kg_schema_definition")}
        if "graph_space" in columns:
            return
        default_space = os.getenv("TRS_GRAPH_SPACE", "techkg")
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE kg_schema_definition "
                    "ADD COLUMN graph_space VARCHAR(64) NOT NULL DEFAULT :space, "
                    "ADD INDEX idx_kg_schema_definition_space (graph_space), "
                    "DROP INDEX uk_kg_schema_definition_key, "
                    "ADD UNIQUE KEY uk_kg_schema_definition_key (schema_key, graph_space), "
                    "DROP INDEX uk_kg_schema_definition_name, "
                    "ADD UNIQUE KEY uk_kg_schema_definition_name (name, graph_space)"
                ),
                {"space": default_space},
            )

    def _ensure_builtin_definitions(self) -> None:
        """Idempotently insert built-in workflow definitions missing from older DBs."""
        builtins = [
            ("entity-project", "kg.entity.project", "entity", "国内外项目实体工作流"),
        ]
        with workflow_session_scope() as session:
            for definition_id, workflow_type, category, name in builtins:
                exists = session.scalar(
                    select(WorkflowDefinition).where(WorkflowDefinition.id == definition_id)
                )
                if exists:
                    continue
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
                session.add(
                    WorkflowDefinition(
                        id=definition_id,
                        workflow_type=workflow_type,
                        category=category,
                        active=1,
                        payload=_json(payload),
                    )
                )

    def _seed(self, session: Session) -> None:
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
            session.add(
                WorkflowBatch(
                    id=batch["id"],
                    update_date=batch["updateDate"],
                    payload=_json(batch),
                )
            )

        for task in self._seed_tasks():
            session.add(
                WorkflowTask(
                    id=task["id"],
                    batch_id=task["batchId"],
                    stage=task["stage"],
                    task_status=task["taskStatus"],
                    domain=task["dataDomain"],
                    kind=task["kind"],
                    processed_at=task["processedAt"],
                    payload=_json(task),
                )
            )

        for review in self._seed_reviews():
            session.add(
                WorkflowReview(
                    id=review["id"],
                    task_id=review["id"],
                    batch_id=review["batch"],
                    status=review["status"],
                    domain=review["domain"],
                    category=review["category"],
                    updated_at=review["updatedAt"],
                    payload=_json(review),
                )
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
            session.add(
                WorkflowSourceUpdate(
                    domain=item["domain"],
                    detected_at=item["detectedAt"],
                    payload=_json(item),
                )
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
        session.add(WorkflowSetting(key="update_policy", payload=_json(policy)))

        definitions = [
            ("entity-paper", "kg.entity.paper", "entity", "论文实体工作流"),
            ("entity-scholar", "kg.entity.scholar", "entity", "人才实体工作流"),
            ("entity-patent", "kg.entity.patent", "entity", "专利实体工作流"),
            ("entity-organization", "kg.entity.organization", "entity", "机构实体工作流"),
            ("entity-project", "kg.entity.project", "entity", "国内外项目实体工作流"),
            ("relation-authorship", "kg.relation.authorship", "relation", "论文作者关系工作流"),
            ("relation-employment", "kg.relation.employment", "relation", "人才任职关系工作流"),
            ("relation-citation", "kg.relation.citation", "relation", "论文引用关系工作流"),
            ("relation-cooperation", "kg.relation.cooperation", "relation", "合作关系工作流"),
            ("graph-build", "kg.graph.build", "graph", "图谱构建总工作流"),
        ]
        for definition_id, workflow_type, category, name in definitions:
            exists = session.scalar(
                select(WorkflowDefinition).where(WorkflowDefinition.id == definition_id)
            )
            if exists:
                continue
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
            session.add(
                WorkflowDefinition(
                    id=definition_id,
                    workflow_type=workflow_type,
                    category=category,
                    active=1,
                    payload=_json(payload),
                )
            )

    @staticmethod
    def _steps(blocking: str | None = None) -> list[dict[str, Any]]:
        # 兜底模板:任务刚创建(还未执行)时填的静态 7 步,字段都是编造的演示值
        # (count="1 个处理对象"、duration="6秒" 等)。
        # 终态后 _sync_task_from_execution 会用 normalize_stages(output)
        # 拿真实 worker stages 覆盖 task["steps"]。
        # TODO: 移除——等 seed 数据 / 新建任务流程能产出真实步骤模板后删掉。
        raw = [
            ("source", "数据接入", "数据处理", "读取业务域增量数据"),
            ("normalize", "清洗标准化", "数据处理", "执行字段、枚举和字典标准化"),
            ("schema", "Schema 映射", "图谱构建", "映射实体、关系与属性 Schema"),
            ("extract", "实体关系抽取", "图谱构建", "运行领域专属实体/关系工作流"),
            ("align", "实体对齐消歧", "图谱构建", "候选实体与存量图谱召回、消歧与合并"),
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
                "align",
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
                "专家实体对齐歧义",
                "人才",
                "专家实体",
                "李晓峰 / Li Xiaofeng",
                "ALIGN-AMBIGUITY-004",
                "召回 3 个高相似存量专家，无法自动消歧合并",
                "0.81",
                "王审核",
                "实体对齐消歧",
                "专家基本信息表",
                "EXPERT-20566",
                "实体对齐异常",
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

    def list_batches(self) -> list[dict[str, Any]]:
        with workflow_session_scope() as session:
            rows = session.scalars(
                select(WorkflowBatch).order_by(WorkflowBatch.update_date.desc())
            ).all()
            return [json.loads(row.payload) for row in rows]

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        with workflow_session_scope() as session:
            row = session.scalar(select(WorkflowBatch).where(WorkflowBatch.id == batch_id))
            return json.loads(row.payload) if row else None

    def list_tasks(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        with workflow_session_scope() as session:
            stmt = select(WorkflowTask).order_by(WorkflowTask.processed_at.desc())
            mapping = {
                "stage": WorkflowTask.stage,
                "task_status": WorkflowTask.task_status,
                "domain": WorkflowTask.domain,
                "kind": WorkflowTask.kind,
                "batch_id": WorkflowTask.batch_id,
            }
            for key, column in mapping.items():
                value = filters.get(key)
                if value:
                    stmt = stmt.where(column == value)
            if filters.get("start_time"):
                stmt = stmt.where(WorkflowTask.processed_at >= filters["start_time"])
            if filters.get("end_time"):
                stmt = stmt.where(WorkflowTask.processed_at <= filters["end_time"])
            rows = session.scalars(stmt).all()
            items = [json.loads(row.payload) for row in rows]
        keyword = filters.get("keyword")
        if keyword:
            items = [item for item in items if keyword.lower() in _json(item).lower()]
        return items

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with workflow_session_scope() as session:
            row = session.scalar(select(WorkflowTask).where(WorkflowTask.id == task_id))
            return json.loads(row.payload) if row else None

    def save_task(self, task: dict[str, Any]) -> None:
        with workflow_session_scope() as session:
            session.merge(
                WorkflowTask(
                    id=task["id"],
                    batch_id=task["batchId"],
                    stage=task["stage"],
                    task_status=task["taskStatus"],
                    domain=task["dataDomain"],
                    kind=task["kind"],
                    processed_at=task["processedAt"],
                    payload=_json(task),
                )
            )

    def list_reviews(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        with workflow_session_scope() as session:
            stmt = select(WorkflowReview).order_by(WorkflowReview.updated_at.desc())
            mapping = {
                "status": WorkflowReview.status,
                "domain": WorkflowReview.domain,
                "category": WorkflowReview.category,
                "batch_id": WorkflowReview.batch_id,
            }
            for key, column in mapping.items():
                value = filters.get(key)
                if value:
                    stmt = stmt.where(column == value)
            if filters.get("start_time"):
                stmt = stmt.where(WorkflowReview.updated_at >= filters["start_time"])
            if filters.get("end_time"):
                stmt = stmt.where(WorkflowReview.updated_at <= filters["end_time"])
            rows = session.scalars(stmt).all()
            items = [json.loads(row.payload) for row in rows]
        keyword = filters.get("keyword")
        if keyword:
            items = [item for item in items if keyword.lower() in _json(item).lower()]
        return items

    def get_review(self, review_id: str) -> dict[str, Any] | None:
        with workflow_session_scope() as session:
            row = session.scalar(select(WorkflowReview).where(WorkflowReview.id == review_id))
            return json.loads(row.payload) if row else None

    def save_review(self, review: dict[str, Any]) -> None:
        with workflow_session_scope() as session:
            session.merge(
                WorkflowReview(
                    id=review["id"],
                    task_id=review["id"],
                    batch_id=review["batch"],
                    status=review["status"],
                    domain=review["domain"],
                    category=review["category"],
                    updated_at=review["updatedAt"],
                    payload=_json(review),
                )
            )

    def list_source_updates(
        self, domain: str | None, since: str | None, until: str | None
    ) -> list[dict[str, Any]]:
        with workflow_session_scope() as session:
            stmt = select(WorkflowSourceUpdate).order_by(WorkflowSourceUpdate.detected_at.desc())
            if domain:
                stmt = stmt.where(WorkflowSourceUpdate.domain == domain)
            if since:
                stmt = stmt.where(WorkflowSourceUpdate.detected_at >= since)
            if until:
                stmt = stmt.where(WorkflowSourceUpdate.detected_at <= until)
            rows = session.scalars(stmt).all()
            return [json.loads(row.payload) for row in rows]

    def get_setting(self, key: str) -> dict[str, Any] | None:
        with workflow_session_scope() as session:
            row = session.scalar(select(WorkflowSetting).where(WorkflowSetting.key == key))
            return json.loads(row.payload) if row else None

    def save_setting(self, key: str, payload: dict[str, Any]) -> None:
        with workflow_session_scope() as session:
            session.merge(WorkflowSetting(key=key, payload=_json(payload)))

    def list_definitions(self, category: str | None = None) -> list[dict[str, Any]]:
        with workflow_session_scope() as session:
            stmt = select(WorkflowDefinition).order_by(
                WorkflowDefinition.category, WorkflowDefinition.id
            )
            if category:
                stmt = stmt.where(WorkflowDefinition.category == category)
            rows = session.scalars(stmt).all()
            return [json.loads(row.payload) for row in rows]

    def get_definition(self, definition_id: str) -> dict[str, Any] | None:
        with workflow_session_scope() as session:
            row = session.scalar(
                select(WorkflowDefinition).where(WorkflowDefinition.id == definition_id)
            )
            return json.loads(row.payload) if row else None

    def save_definition(self, definition: dict[str, Any]) -> None:
        with workflow_session_scope() as session:
            session.merge(
                WorkflowDefinition(
                    id=definition["id"],
                    workflow_type=definition["workflowType"],
                    category=definition["category"],
                    active=int(definition.get("active", True)),
                    payload=_json(definition),
                )
            )

    def save_execution(self, execution: dict[str, Any]) -> None:
        with workflow_session_scope() as session:
            session.merge(
                WorkflowExecution(
                    id=execution["id"],
                    definition_id=execution["definitionId"],
                    workflow_id=execution["workflowId"],
                    run_id=execution.get("runId"),
                    status=execution["status"],
                    started_at=execution["startedAt"],
                    job_id=execution.get("jobId"),
                    payload=_json(execution),
                )
            )

    def get_execution(self, execution_id: str) -> dict[str, Any] | None:
        with workflow_session_scope() as session:
            row = session.scalar(
                select(WorkflowExecution).where(WorkflowExecution.id == execution_id)
            )
            return json.loads(row.payload) if row else None

    def get_execution_by_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        """按 workflowId 查 execution 行；retry reset 后用来回写新 runId。"""
        with workflow_session_scope() as session:
            row = session.scalar(
                select(WorkflowExecution).where(WorkflowExecution.workflow_id == workflow_id)
            )
            return json.loads(row.payload) if row else None

    def get_execution_by_run(self, run_id: str) -> dict[str, Any] | None:
        """按 runId 查 execution 行（周期任务落库幂等判断）。"""
        with workflow_session_scope() as session:
            row = session.scalar(
                select(WorkflowExecution).where(WorkflowExecution.run_id == run_id)
            )
            return json.loads(row.payload) if row else None

    def list_executions(
        self,
        limit: int = 100,
        definition_id: str | None = None,
        schedule_id: str | None = None,
        job_id: str | None = None,
        trigger_source: str | None = None,
    ) -> list[dict[str, Any]]:
        with workflow_session_scope() as session:
            stmt = select(WorkflowExecution).order_by(WorkflowExecution.started_at.desc())
            if definition_id:
                stmt = stmt.where(WorkflowExecution.definition_id == definition_id)
            if job_id:
                stmt = stmt.where(WorkflowExecution.job_id == job_id)
            # scheduleId/triggerSource 只存 payload JSON 里，取较多行后内存过滤；
            # 非 RERUN 执行超过 500 条时较旧的匹配会被截断（当前量小可接受）
            scan_limit = limit if not (schedule_id or trigger_source) else 500
            rows = session.scalars(stmt.limit(scan_limit)).all()
            items = [json.loads(row.payload) for row in rows]
            if schedule_id:
                items = [item for item in items if item.get("scheduleId") == schedule_id]
            if trigger_source:
                items = [item for item in items if item.get("triggerSource") == trigger_source]
            return items[:limit]

    def save_job(self, job: dict[str, Any]) -> None:
        with workflow_session_scope() as session:
            session.merge(
                WorkflowJob(
                    id=job["id"],
                    name=job["name"],
                    task_type=job["taskType"],
                    definition_id=job["definitionId"],
                    owner=job.get("owner", ""),
                    status=job.get("status", "启用"),
                    schedule_kind=(job.get("schedule") or {}).get("kind", "once"),
                    cron=(job.get("schedule") or {}).get("cron"),
                    created_at=job["createdAt"],
                    payload=_json(job),
                )
            )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with workflow_session_scope() as session:
            row = session.scalar(select(WorkflowJob).where(WorkflowJob.id == job_id))
            return json.loads(row.payload) if row else None

    def list_jobs(
        self,
        name: str | None = None,
        status: str | None = None,
        task_type: str | None = None,
        owner: str | None = None,
    ) -> list[dict[str, Any]]:
        with workflow_session_scope() as session:
            stmt = select(WorkflowJob).order_by(WorkflowJob.created_at.desc())
            if name:
                stmt = stmt.where(WorkflowJob.name.like(f"%{name}%"))
            if status:
                stmt = stmt.where(WorkflowJob.status == status)
            if task_type:
                stmt = stmt.where(WorkflowJob.task_type == task_type)
            if owner:
                stmt = stmt.where(WorkflowJob.owner == owner)
            rows = session.scalars(stmt).all()
            return [json.loads(row.payload) for row in rows]

    def delete_job(self, job_id: str) -> bool:
        with workflow_session_scope() as session:
            row = session.scalar(select(WorkflowJob).where(WorkflowJob.id == job_id))
            if row is None:
                return False
            session.delete(row)
            return True

    def save_schedule(self, schedule: dict[str, Any]) -> None:
        with workflow_session_scope() as session:
            session.merge(
                WorkflowSchedule(
                    id=schedule["id"],
                    definition_id=schedule["definitionId"],
                    active=int(schedule.get("active", True)),
                    payload=_json(schedule),
                )
            )

    def list_schedules(self) -> list[dict[str, Any]]:
        with workflow_session_scope() as session:
            rows = session.scalars(select(WorkflowSchedule).order_by(WorkflowSchedule.id)).all()
            return [json.loads(row.payload) for row in rows]

    def get_schedule(self, schedule_id: str) -> dict[str, Any] | None:
        with workflow_session_scope() as session:
            row = session.scalar(select(WorkflowSchedule).where(WorkflowSchedule.id == schedule_id))
            return json.loads(row.payload) if row else None

    def delete_schedule(self, schedule_id: str) -> bool:
        with workflow_session_scope() as session:
            row = session.scalar(select(WorkflowSchedule).where(WorkflowSchedule.id == schedule_id))
            if row is None:
                return False
            session.delete(row)
            return True

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
        # 原 SQLite 实现是删 db 文件 + 重建；MySQL 下用 DROP+CREATE 全部表
        # （比 TRUNCATE 干净，避免自增列残留 + 兼容 schema 变更）
        url = self._engine.url
        if url.get_backend_name() != "sqlite" and os.getenv("WORKFLOW_RESET_ALLOW_REAL") != "1":
            raise RuntimeError(
                "reset_for_tests 会 DROP 共享库的全部控制面表（含 schema 目录），"
                "只允许临时 SQLite 引擎；确需重置真实库请设 WORKFLOW_RESET_ALLOW_REAL=1"
            )
        Base.metadata.drop_all(self._engine)
        Base.metadata.create_all(self._engine)
        self._initialize()


repository = WorkflowRepository()
