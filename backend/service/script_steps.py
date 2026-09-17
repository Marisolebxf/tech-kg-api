"""脚本多步声明解析（上传校验与抽取计划组装共用，纯 ast 无副作用）。

kg.schema.extract 允许用户在脚本里声明多步转换（2026-09-15 并入主通道，替代已下线
的 kg.custom.steps 独立上传通道）。两种声明方式，推荐 ``@step`` 装饰器：

    from kg_sdk import step

    @step                      # step id 默认取函数名，顺序 = 源码出现顺序
    def normalize(payload): ...

    @step("resolve")           # 显式指定 step id（可含 -）
    def do_resolve(payload): ...

兼容旧顶层 ``STEPS`` 清单（id/fn 映射，顺序由清单给出）：

    STEPS = [
        {"id": "normalize", "fn": "step_normalize"},   # 第一步消费平台读的源表行
        {"id": "resolve",   "fn": "step_resolve"},     # 后续步消费上一步输出
        {"id": "emit",      "fn": "step_emit"},
    ]

两种方式都只做 **静态解析**（装饰器与 list 字面量均可从 AST 直接读出），保证上传时
即可校验尽早报错，运行时 ``load_schema_extract_plan`` 无需执行脚本即可展开步清单；
脚本内的 ``kg_sdk.step`` 装饰器在子进程里执行到时只是恒等返回，不参与调度。
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


# ---------------------------------------------------------------------------
# @step 装饰器声明（推荐写法）：顶层函数标注 @step / @step("id")，顺序 = 源码顺序
# ---------------------------------------------------------------------------


def _is_step_decorator_name(expr: ast.expr) -> bool:
    """装饰器名是否指向 step（裸 ``step`` 或点式 ``kg_sdk.step``）。"""
    if isinstance(expr, ast.Name):
        return expr.id == "step"
    if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
        return expr.value.id == "kg_sdk" and expr.attr == "step"
    return False


def _decorator_explicit_id(decorator: ast.expr) -> str | None:
    """解析 ``@step`` / ``@step("id")`` / ``@step(id="id")`` 的显式 id。

    无参形式（含裸 ``@kg_sdk.step``）返回 None（id 落到函数名）；形状非法（非字符
    串常量、多参数等）抛 ``ValueError``。调用方需先用 :func:`_is_step_decorator_name`
    确认是 step 装饰器。
    """
    if not isinstance(decorator, ast.Call):
        return None
    args = decorator.args
    keywords = decorator.keywords
    if not args and not keywords:
        return None
    explicit: ast.expr | None = None
    if len(args) == 1 and not keywords:
        explicit = args[0]
    elif not args and len(keywords) == 1 and keywords[0].arg == "id":
        explicit = keywords[0].value
    if (
        explicit is None
        or not isinstance(explicit, ast.Constant)
        or not isinstance(explicit.value, str)
    ):
        raise ValueError('step 装饰器只接受一个可选的 step id 字符串常量（如 @step("resolve")）')
    step_id = explicit.value
    if not step_id.strip():
        raise ValueError("step 装饰器的 id 不能为空白字符串")
    return step_id


def _decorated_steps_from_tree(tree: ast.Module) -> list[dict[str, str]]:
    """收集顶层 ``@step`` 标注的函数，按源码出现顺序生成步清单。

    未标注任何函数返回空列表；函数名作默认 id（中文/超长函数名不匹配 id 字符集，
    需显式传 ASCII id）。异步函数与同步函数同样接受（runner 会 await）。
    """
    steps: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if any(_is_step_decorator_name(_decorator_target(d)) for d in node.decorator_list):
                raise ValueError("step 装饰器只能标注在函数上，不能标注类")
            continue
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        explicit_ids: list[str | None] = []
        for decorator in node.decorator_list:
            target = _decorator_target(decorator)
            if _is_step_decorator_name(target):
                explicit_ids.append(_decorator_explicit_id(decorator))
        if not explicit_ids:
            continue
        if len(explicit_ids) > 1:
            raise ValueError(f"函数 {node.name} 重复标注 step 装饰器")
        explicit = explicit_ids[0]
        step_id = explicit if explicit is not None else node.name
        if not _STEP_ID_PATTERN.fullmatch(step_id):
            hint = (
                f'（函数名 {node.name!r} 不能直接作 step id，请用 @step("...") 显式指定 ASCII id）'
                if explicit is None
                else ""
            )
            raise ValueError(
                f"step 装饰器声明的 id 非法: {step_id!r}（须匹配 [A-Za-z0-9_-]{{1,64}}）{hint}"
            )
        if step_id in seen_ids:
            raise ValueError(f"step 装饰器声明的 id 重复: {step_id}")
        seen_ids.add(step_id)
        steps.append({"id": step_id, "fn": node.name})
    if len(steps) > MAX_STEPS:
        raise ValueError(f"@step 声明最长 {MAX_STEPS} 步，当前 {len(steps)} 步")
    return steps


def _decorator_target(decorator: ast.expr) -> ast.expr:
    """取装饰器表达式指向的名字（``@step("x")`` 取 Call.func，裸装饰器原样返回）。"""
    if isinstance(decorator, ast.Call):
        return decorator.func
    return decorator


def _has_steps_literal(tree: ast.Module) -> bool:
    """顶层是否存在 STEPS 赋值（只做存在性检查，形状校验留给 step_list_from_tree）。"""
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            if isinstance(node.targets[0], ast.Name) and node.targets[0].id == "STEPS":
                return True
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "STEPS":
                return True
    return False


def declared_steps_from_tree(tree: ast.Module) -> list[dict[str, str]] | None:
    """合并的多步声明入口：``@step`` 装饰器（推荐）或顶层 ``STEPS`` 清单（兼容）。

    返回步清单（顺序即执行顺序）；两种声明都未出现返回 None（单步脚本）。
    同时声明两种 → 报歧义；顶层 ``transform`` 与任一多步声明共存 → 报歧义。
    """
    functions = {
        node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    decorated = _decorated_steps_from_tree(tree)
    if decorated:
        if _has_steps_literal(tree):
            raise ValueError("@step 装饰器与 STEPS 清单不能同时声明：请只保留一种多步声明方式")
        if "transform" in functions:
            raise ValueError("transform 与 @step 不能同时声明：多步脚本请删除顶层 transform 入口")
        return decorated
    return step_list_from_tree(tree)


def extract_declared_steps(
    source: str, *, filename: str = "<script>"
) -> list[dict[str, str]] | None:
    """解析源码里的多步声明（``@step`` 装饰器优先，其次顶层 ``STEPS`` 清单）。

    返回 ``[{"id": ..., "fn": ...}, ...]``；两种声明都没有返回 None（单步脚本）。
    声明存在但非法时抛 ``ValueError``（中文原因，上传侧包装成 SchemaScriptError）。
    """
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        raise ValueError(f"Python 脚本语法错误（第 {exc.lineno or 0} 行）: {exc.msg}") from exc
    return declared_steps_from_tree(tree)
