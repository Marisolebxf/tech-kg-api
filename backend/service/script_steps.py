"""脚本 STEPS 多步声明解析（上传校验与抽取计划组装共用，纯 ast 无副作用）。

kg.schema.extract 允许用户在脚本顶层用 ``STEPS`` 清单声明多步转换（2026-09-15
并入主通道，替代已下线的 kg.custom.steps 独立上传通道）：

    STEPS = [
        {"id": "normalize", "fn": "step_normalize"},   # 第一步消费平台读的源表行
        {"id": "resolve",   "fn": "step_resolve"},     # 后续步消费上一步输出
        {"id": "emit",      "fn": "step_emit"},
    ]

只认 **list 字面量**（元素为 dict 字面量、id/fn 为字符串常量），保证上传时即可
静态校验尽早报错，运行时 ``load_schema_extract_plan`` 无需执行脚本即可展开步清单。
"""

from __future__ import annotations

import ast
import re

# step id 允许的字符集（与任务/审核 case 的观测标识兼容，不含 # : 等分隔符）
_STEP_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# 步数上限：每步输出都要经 activity 结果/输入在 gRPC 与 workflow 事件历史间往返，
# 步数过多会放大单条请求与事件事务体积（参见 _MAX_BATCH_ROWS_BYTES 的教训）
MAX_STEPS = 16


def extract_step_list(source: str, *, filename: str = "<script>") -> list[dict[str, str]] | None:
    """解析源码顶层 ``STEPS = [...]`` 声明。

    返回 ``[{"id": ..., "fn": ...}, ...]``；未声明 STEPS 返回 None（单步脚本）。
    声明存在但非法时抛 ``ValueError``（中文原因，上传侧包装成 SchemaScriptError）。
    """
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        raise ValueError(f"Python 脚本语法错误（第 {exc.lineno or 0} 行）: {exc.msg}") from exc
    return step_list_from_tree(tree)


def step_list_from_tree(tree: ast.Module) -> list[dict[str, str]] | None:
    """从已解析的 AST 里取顶层 STEPS 清单；规则同 :func:`extract_step_list`。"""
    functions = {
        node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    literal: ast.List | None = None
    for node in tree.body:
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id == "STEPS":
                value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "STEPS":
                value = node.value
        if value is not None:
            if not isinstance(value, ast.List):
                raise ValueError(
                    'STEPS 必须赋值为 list 字面量（如 STEPS = [{"id": ..., "fn": ...}]）'
                )
            literal = value  # 多次赋值取最后一次（与 Python 执行语义一致）
    if literal is None:
        return None
    if "transform" in functions:
        raise ValueError("transform 与 STEPS 不能同时声明：多步脚本请删除顶层 transform 入口")
    if not literal.elts:
        raise ValueError("STEPS 清单不能为空")
    steps: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for position, element in enumerate(literal.elts, start=1):
        try:
            item = ast.literal_eval(element)
        except ValueError as exc:
            raise ValueError(
                f"STEPS 第 {position} 项必须是 dict 字面量（id/fn 均为字符串常量）"
            ) from exc
        if not isinstance(item, dict):
            raise ValueError(f"STEPS 第 {position} 项必须是 dict 字面量")
        step_id = item.get("id")
        fn = item.get("fn")
        if not isinstance(step_id, str) or not step_id.strip():
            raise ValueError(f"STEPS 第 {position} 项缺少非空字符串 id")
        if not _STEP_ID_PATTERN.fullmatch(step_id):
            raise ValueError(
                f"STEPS 第 {position} 项 id 非法: {step_id!r}（须匹配 [A-Za-z0-9_-]{{1,64}}）"
            )
        if step_id in seen_ids:
            raise ValueError(f"STEPS 中 id 重复: {step_id}")
        if not isinstance(fn, str) or not fn.strip():
            raise ValueError(f"STEPS 第 {position} 项缺少非空字符串 fn")
        if fn not in functions:
            raise ValueError(f"STEPS 引用的函数 {fn} 未在脚本顶层定义")
        seen_ids.add(step_id)
        steps.append({"id": step_id, "fn": fn})
    if len(steps) > MAX_STEPS:
        raise ValueError(f"STEPS 清单最长 {MAX_STEPS} 步，当前 {len(steps)} 步")
    return steps
