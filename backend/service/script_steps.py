"""脚本多步声明解析（上传校验与抽取计划组装共用，纯 ast 无副作用）。

kg.schema.extract 只接受一种脚本声明方式：顶层函数标 ``@step`` 装饰器
（2026-09-17 收敛：单步 ``transform`` 入口与旧 ``STEPS`` 清单链路已删除）：

    from kg_sdk import step

    @step                      # step id 默认取函数名，顺序 = 源码出现顺序
    def normalize(payload): ...

    @step("resolve")           # 显式指定 step id（可含 -）
    def do_resolve(payload): ...

第 1 步消费平台读的源表行（``payload["rows"]``），第 N>1 步消费上一步输出
（``payload["input"]``）。只做 **静态解析**（装饰器可从 AST 直接读出），保证
上传时即可校验尽早报错，运行时 ``load_schema_extract_plan`` 无需执行脚本即可
展开步清单；脚本内的 ``kg_sdk.step`` 装饰器在子进程里执行到时只是恒等返回，
不参与调度。
"""

from __future__ import annotations

import ast
import re

# step id 允许的字符集（与任务/审核 case 的观测标识兼容，不含 # : 等分隔符）
_STEP_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# 步数上限：每步输出都要经 activity 结果/输入在 gRPC 与 workflow 事件历史间往返，
# 步数过多会放大单条请求与事件事务体积（参见 _MAX_BATCH_ROWS_BYTES 的教训）
MAX_STEPS = 16

# 已删除的旧入口名（出现即报错，提示迁移到 @step）
_LEGACY_ENTRIES = ("transform", "workflow")


def extract_declared_steps(source: str, *, filename: str = "<script>") -> list[dict[str, str]]:
    """解析源码顶层的 ``@step`` 装饰器声明，返回步清单（顺序即执行顺序）。

    无任何 ``@step``、或残留 transform/STEPS 旧声明时抛 ``ValueError``
    （中文原因，上传侧包装成 SchemaScriptError）。
    """
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        raise ValueError(f"Python 脚本语法错误（第 {exc.lineno or 0} 行）: {exc.msg}") from exc
    return declared_steps_from_tree(tree)


def declared_steps_from_tree(tree: ast.Module) -> list[dict[str, str]]:
    """从已解析的 AST 里取 ``@step`` 步清单；规则同 :func:`extract_declared_steps`。"""
    if _has_steps_literal(tree):
        raise ValueError("STEPS 清单声明已下线：请改用 @step 装饰器声明抽取步")
    steps = _decorated_steps_from_tree(tree)
    functions = {
        node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if steps:
        legacy = [name for name in _LEGACY_ENTRIES if name in functions]
        if legacy:
            raise ValueError(
                f"@step 与旧入口 {'/'.join(legacy)} 不能同时声明：旧入口已下线，请删除"
            )
        return steps
    legacy = [name for name in _LEGACY_ENTRIES if name in functions]
    if legacy:
        raise ValueError(f"单步 {'/'.join(legacy)} 入口已下线：请用 @step 装饰器声明至少一个抽取步")
    raise ValueError("脚本缺少抽取步声明：请用 @step 装饰器声明至少一个抽取步")


# ---------------------------------------------------------------------------
# @step 装饰器声明：顶层函数标注 @step / @step("id")，顺序 = 源码出现顺序
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
    """顶层是否存在 STEPS 赋值（只做存在性检查，用于给出下线提示）。"""
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            if isinstance(node.targets[0], ast.Name) and node.targets[0].id == "STEPS":
                return True
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "STEPS":
                return True
    return False
