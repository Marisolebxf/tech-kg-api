"""本地离线验证器：零数据库 / 零图库 / 零 Temporal，验证本目录三个抽取脚本。

复用平台**真实**代码（不重新发明口径）：

- ``backend/service/script_steps.py::extract_declared_steps`` —— 上传校验同款
  AST 解析（@step 声明能被平台识别才算过）；
- ``backend/service/entity_disambiguation.py::score_candidate/decide`` ——
  写前消歧同款打分/决策（模拟「图内已有第一轮种子实体，第二轮同名实体
  进来」的召回比对，预测 merge / gray(T_LINK) / new 三分支）。

运行方式（仓库任意位置均可，路径按文件位置自适应）：

    backend/.venv/bin/python docs/抽取脚本示例/失败重跑与写前消歧/本地验证.py

断言内容：

1. 三个脚本均被平台解析器识别为多步（@step 声明合法、步序正确）；
2. 失败重跑脚本：3 毒行 → 3 failures（recordId 必填非空——平台
   ``_shape_step_failures`` 的硬性要求），3 好行 → 3 实体；
3. 写前消歧脚本：第一轮 4 实体；第二轮 4 实体经真实打分器预测——
   E2001 merge / E2002 gray / E2003 new / E2004 gray（与 demo_数据.sql
   注释里的预期表一致）；
4. 关系挂起脚本：2 边 + 2 pendingReview（字段口径完整）+ 2 failures；
5. 全部输出形状满足平台契约（entities[{id,props}] / edges[{fromId,toId,props}] /
   failures[{recordId,error}] / pendingReview 关键字段）。

任何断言失败 → 非 0 退出。改动脚本或数据后先跑本文件再上传平台。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_THIS_DIR = Path(__file__).resolve().parent
# 向上探测仓库根（兼容普通 checkout 与 .claude/worktrees/<name> 里的额外层级）
_REPO_ROOT = next(
    parent
    for parent in _THIS_DIR.parents
    if (parent / "backend" / "sdk" / "kg_sdk.py").is_file()
)
_BACKEND = _REPO_ROOT / "backend"
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_BACKEND / "sdk"))

from service.entity_disambiguation import (
    decide,
    display_name,
    normalize_display_name,
    score_candidate,
)
from service.script_steps import extract_declared_steps


def load_script(path: Path) -> tuple[Any, list[dict[str, str]]]:
    """加载脚本模块并返回 (module, 平台解析出的步清单)。"""
    source = path.read_text(encoding="utf-8")
    steps = extract_declared_steps(source, filename=path.name)
    if not steps:
        raise AssertionError(f"{path.name}: 平台解析器未识别到多步声明（@step）")
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module, steps


def run_chain(module: Any, steps: list[dict[str, str]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """模拟平台执行：第 1 步喂 rows，第 N>1 步喂 {"input": 上一步输出}。

    返回跨步聚合结果（failures 跨步聚合、entities/edges/pendingReview
    任意步出记录即计入——与平台语义一致）。
    """
    meta = {
        "source_table": "techkg_script_demo.demo",
        "kind": "entity",
        "source": {"id": "src-demo", "pkColumn": "id"},
    }
    payload: dict[str, Any] = {**meta, "rows": rows}
    aggregated: dict[str, Any] = {"entities": [], "edges": [], "failures": [], "pendingReview": []}
    for step in steps:
        out = getattr(module, step["fn"])(payload)
        for key in ("entities", "edges", "failures", "pendingReview"):
            aggregated[key].extend(out.get(key) or [])
        payload = {"input": out, **meta}
    return aggregated


def assert_contract(result: dict[str, Any], *, label: str) -> None:
    """平台输出契约硬性检查（recordId 为 None 的 failures 会被平台整条丢弃）。"""
    for entity in result["entities"]:
        assert isinstance(entity.get("id"), str) and entity["id"], f"{label}: 实体缺 id"
        assert isinstance(entity.get("props"), dict), f"{label}: 实体缺 props"
    for edge in result["edges"]:
        assert edge.get("fromId") and edge.get("toId") and isinstance(edge.get("props"), dict), (
            f"{label}: 边缺 fromId/toId/props"
        )
    for failure in result["failures"]:
        assert failure.get("recordId") is not None, f"{label}: failure.recordId 为 None（平台会丢弃）"
        assert str(failure["recordId"]).strip(), f"{label}: failure.recordId 为空串"
    for item in result["pendingReview"]:
        for key in ("kind", "candidate", "objectId", "objectName", "edgeType", "reason"):
            assert key in item, f"{label}: pendingReview 项缺字段 {key}"
        assert item["candidate"].get("reason"), f"{label}: pendingReview.candidate.reason 为空"


def predict_disambiguation(
    incoming: list[dict[str, Any]], graph_entities: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """用平台真实 score_candidate/decide 预测写前消歧判定。

    模拟 resolve_entity_batch 的召回（图内同名精确匹配）+ 逐候选评分 + 三分支。
    """
    predictions: dict[str, dict[str, Any]] = {}
    for record in incoming:
        name = display_name(record["props"])
        candidates = [
            {
                "vid": existing["id"],
                "name": display_name(existing["props"]),
                "props": existing["props"],
            }
            for existing in graph_entities
            if normalize_display_name(display_name(existing["props"])) == normalize_display_name(name)
        ]
        scored = [
            {
                "vid": cand["vid"],
                "name": cand["name"],
                "score": score_candidate(name, record["props"], cand["name"], cand["props"])[0],
                "detail": score_candidate(name, record["props"], cand["name"], cand["props"])[1],
            }
            for cand in candidates
        ]
        predictions[record["props"].get("id") or record["id"]] = decide(scored) | {
            "scored": scored,
            "incomingVid": record["id"],
        }
    return predictions


def main() -> int:
    try:
        # ── 1. 失败重跑脚本：3 好行 + 3 毒行 ────────────────────────────────
        module, steps = load_script(_THIS_DIR / "失败重跑_产品实体.py")
        assert [s["id"] for s in steps] == ["normalize", "emit"], "失败重跑脚本步序应为 normalize→emit"
        rows = [
            {"id": 1, "product_name": "智能语音识别系统", "product_seq": "P-2024-001",
             "company_name": "杭州云声科技有限公司", "credit_code": "91330100MA2XYZ1234"},
            {"id": 2, "product_name": "工业视觉检测平台", "product_seq": "P-2024-002",
             "company_name": "苏州视锐智能装备有限公司", "credit_code": "91320594MA1ABC5678"},
            {"id": 3, "product_name": "车规级激光雷达", "product_seq": "P-2024-003",
             "company_name": "上海光启传感技术有限公司", "credit_code": "91310115MA3DEF9012"},
            {"id": 4, "product_name": "", "product_seq": "P-2024-004",
             "company_name": "某某科技有限公司", "credit_code": "91330100MA2POI0987"},
            {"id": 5, "product_name": "   ", "product_seq": "P-2024-005",
             "company_name": "某某科技有限公司", "credit_code": "91330100MA2POI0987"},
            {"id": 6, "product_name": "N/A", "product_seq": "P-2024-006",
             "company_name": "某某科技有限公司", "credit_code": "91330100MA2POI0987"},
        ]
        result = run_chain(module, steps, rows)
        assert_contract(result, label="失败重跑")
        assert len(result["entities"]) == 3, f"期望 3 实体，得到 {len(result['entities'])}"
        assert len(result["failures"]) == 3, f"期望 3 failures，得到 {len(result['failures'])}"
        assert {f["recordId"] for f in result["failures"]} == {"4", "5", "6"}, "毒行 recordId 应为 4/5/6"
        print("✓ 失败重跑_产品实体.py：3 实体 + 3 毒行 failures（→ T_EXTRACT_FAIL 可重跑）")

        # ── 2. 写前消歧脚本：第一轮种子 + 第二轮冲突 ────────────────────────
        module, steps = load_script(_THIS_DIR / "写前消歧_同名专家.py")
        assert [s["id"] for s in steps] == ["normalize", "emit"], "消歧脚本步序应为 normalize→emit"
        seed_rows = [
            {"id": 101, "expert_id": "E1001", "name_zh": "王伟",
             "organization_name_zh": "清华大学", "bio_zh": "自然语言处理方向"},
            {"id": 102, "expert_id": "E1002", "name_zh": "李娜",
             "organization_name_zh": "北京大学", "bio_zh": "计算机视觉方向"},
            {"id": 103, "expert_id": "E1003", "name_zh": "张敏",
             "organization_name_zh": "复旦大学", "bio_zh": "数据库系统方向"},
            {"id": 104, "expert_id": "E1004", "name_zh": "刘洋",
             "organization_name_zh": "浙江大学", "bio_zh": None},
        ]
        round1 = run_chain(module, steps, seed_rows)
        assert_contract(round1, label="消歧#1")
        assert len(round1["entities"]) == 4 and not round1["failures"], "第一轮应 4 实体 0 失败"
        print("✓ 写前消歧_同名专家.py 第一轮：4 种子实体（图内无同名 → 全部直写）")

        conflict_rows = [
            {"id": 105, "expert_id": "E2001", "name_zh": "王伟",
             "organization_name_zh": "清华大学", "bio_zh": "自然语言处理方向"},
            {"id": 106, "expert_id": "E2002", "name_zh": "李娜",
             "organization_name_zh": "北京大学", "bio_zh": "机器学习与图像识别方向"},
            {"id": 107, "expert_id": "E2003", "name_zh": "张敏",
             "organization_name_zh": "上海交通大学", "bio_zh": "分布式系统方向"},
            {"id": 108, "expert_id": "E2004", "name_zh": "刘洋",
             "organization_name_zh": None, "bio_zh": "集成电路与芯片设计方向"},
        ]
        round2 = run_chain(module, steps, conflict_rows)
        assert_contract(round2, label="消歧#2")
        assert len(round2["entities"]) == 4 and not round2["failures"], "第二轮应 4 实体 0 失败"

        predictions = predict_disambiguation(round2["entities"], round1["entities"])
        expected = {
            "E2001": ("merge", "expert_E1001"),  # 2/2 属性一致 → 1.00 自动并入
            "E2002": ("gray", "expert_E1002"),   # 1/2 → 0.80 灰区 T_LINK 扣留
            "E2003": ("new", None),              # 0/2 → 0.60 新建直写
            "E2004": ("gray", "expert_E1004"),   # 无可比属性 → 0.5 → 0.80 灰区
        }
        for expert_id, (want_decision, want_target) in expected.items():
            got = predictions[expert_id]
            assert got["decision"] == want_decision, (
                f"{expert_id}: 期望 {want_decision}，打分器判 {got['decision']} "
                f"(score={got['score']}, detail={got['scored']})"
            )
            assert got["targetVid"] == want_target, f"{expert_id}: 目标 vid 不符"
            print(
                f"✓ 消歧预测 {expert_id}: {got['decision']}"
                f"（score={got['score']} → "
                f"{'自动并入 ' + str(want_target) if want_decision == 'merge' else want_decision}）"
            )

        # ── 3. 关系挂起脚本 ─────────────────────────────────────────────────
        module, steps = load_script(_THIS_DIR / "关系挂起_任职边.py")
        assert [s["id"] for s in steps] == ["normalize", "resolve", "emit"], \
            "关系脚本步序应为 normalize→resolve→emit"
        rel_rows = [
            {"id": 1, "expert_id": "E1001", "expert_name": "王伟", "org_name": "浙江大学",
             "position": "兼职教授", "start_date": "2015-09-01"},
            {"id": 2, "expert_id": "E2002", "expert_name": "李娜", "org_name": "中国科学院",
             "position": "兼职研究员", "start_date": "2022-06-01"},
            {"id": 3, "expert_id": "E1003", "expert_name": "张敏", "org_name": "华科",
             "position": "客座研究员", "start_date": "2020-03-01"},
            {"id": 4, "expert_id": "E1004", "expert_name": "刘洋", "org_name": "未来科技大学",
             "position": "副教授", "start_date": "2019-07-01"},
            {"id": 5, "expert_id": None, "expert_name": "未知专家", "org_name": "浙江大学",
             "position": "研究员", "start_date": "2021-01-01"},
            {"id": 6, "expert_id": "E1002", "expert_name": "李娜", "org_name": None,
             "position": "研究员", "start_date": "2018-09-01"},
        ]
        result = run_chain(module, steps, rel_rows)
        assert_contract(result, label="关系挂起")
        assert len(result["edges"]) == 2, f"期望 2 边，得到 {len(result['edges'])}"
        assert len(result["pendingReview"]) == 2, f"期望 2 pendingReview，得到 {len(result['pendingReview'])}"
        assert len(result["failures"]) == 2, f"期望 2 failures，得到 {len(result['failures'])}"
        reasons = " | ".join(str(i["reason"]) for i in result["pendingReview"])
        assert "2 个候选" in reasons and "未在别名表中命中" in reasons, "挂起原因应含多义与未命中"
        print("✓ 关系挂起_任职边.py：2 边 + 2 pendingReview（多义/未命中）+ 2 毒行 failures")
        print()
        print("全部通过：三个脚本的平台契约、毒行 failures、消歧三分支预测均符合预期。")
        print("（本验证零数据库/零图库连接；上平台真跑见 README「隔离运行手册」）")
    except AssertionError as exc:
        print(f"✗ 验证失败: {exc}")
        raise SystemExit(1) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
