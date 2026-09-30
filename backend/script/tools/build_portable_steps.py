"""把 yunfei_restore 适配层脚本生成成自包含可上传脚本（单文件、零 script.* 依赖）。

背景：薄适配层 ``from script.xxx import yyy as legacy`` 依赖整个 backend 仓库的
script.* 包。目标是「开新图空间 + 新 MySQL 库 + 建 Schema/来源绑定后，上传脚本
单文件即可跑」：产物只允许依赖 stdlib / venv 第三方 / kg_sdk 平台契约。

做法（纯 AST，不执行任何脚本代码）：
1. 从入口（适配层的 legacy ``transform`` / 自研文件的 script.* 导入符号）出发递归
   计算符号闭包，跨模块取源码段（含装饰器）；
2. 模块级可执行块（如 catalog 的 ``for`` 填充 SPECS_BY_KEY）作为伪符号一并内联，
   否则机构域关系会静默产出空；
3. 段内函数局部的 ``from script.* import`` 语句剔除（内联后同名符号已在模块层）；
4. 重依赖换成平台 ctx 桥：mysql_engine→ctx.mysql.engine、graph_client→ctx.graph
   租用代理（close 为 no-op，防调用方 finally close 杀掉共享客户端）、
   private_state_dir→tempfile；``except GraphRequestError`` 放宽为 Exception
   （``exc.body`` 改 getattr）；TRSGraphClient/TRSGraphSettings 注解降级 Any；
5. 末尾追加 ``@step("<id>")`` 入口（id 优先沿用文件里已有的显式 id，否则按文件名）。

用法::

    uv run python script/tools/build_portable_steps.py            # 全量写回
    uv run python script/tools/build_portable_steps.py --check    # 只构建不写，报告行数
    uv run python script/tools/build_portable_steps.py --verify   # 对产物做未定义名校验

自研文件（organization_base_mixin / studied_at_relation）：本体保留，仅内联其
script.* 导入符号并清洗 import/类型。
"""

from __future__ import annotations

import argparse
import ast
import builtins
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
RESTORE_DIR = BACKEND / "script" / "yunfei_restore"
# 自研（非薄适配层）脚本：走「本体保留 + 内联其 script.* 导入」路径
SELF_FILES = {"organization_base_mixin.py", "studied_at_relation.py"}

BANNED_PREFIXES = ("script.", "infra.", "utils.")
BANNED_TOPLEVEL = ("script", "infra", "utils")
TYPE_DEMOTION = {"TRSGraphClient": "Any", "TRSGraphSettings": "Any"}

GRAPH_BRIDGE = '''class _LeasedGraphClient:
    """ctx 图客户端的租用视图：属性透传，close/connect 为 no-op。

    老脚本每次 ``graph_client()`` 都新建客户端并在 finally 里 close；平台 ctx
    客户端是任务进程共享的，直接 close 会让本步后续查询全部失败。
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def connect(self) -> None:
        pass

    def close(self) -> None:
        pass


def graph_client() -> Any:
    """平台注入版：任务所选图空间的 trs-graph 客户端（租用视图，close 无害）。"""
    from kg_sdk import current_context

    ctx = current_context()
    client = getattr(ctx, "graph", None) if ctx is not None else None
    if client is None:
        raise RuntimeError("本抽取脚本需要平台注入图客户端（任务/Schema 抽取请在触发时选择图空间）")
    return _LeasedGraphClient(client)'''

MYSQL_BRIDGE = '''def mysql_engine(database: str = "") -> Any:
    """平台注入版：任务所选数据源的 engine（database 形参保留以兼容旧签名）。"""
    from kg_sdk import current_context

    ctx = current_context()
    client = getattr(ctx, "mysql", None) if ctx is not None else None
    if client is None:
        raise RuntimeError("本抽取脚本需要平台注入 MySQL 数据源（任务/Schema 抽取请在触发时选择数据源配置）")
    return client.engine'''

STATE_DIR_BRIDGE = '''def private_state_dir(*parts: str) -> Path:
    """平台注入版：报告落盘用临时目录（老 var/ 私有目录在容器外无意义）。"""
    import tempfile

    return Path(tempfile.gettempdir()).joinpath(*parts)'''

BRIDGES: dict[str, str] = {
    "graph_client": GRAPH_BRIDGE,
    "mysql_engine": MYSQL_BRIDGE,
    "private_state_dir": STATE_DIR_BRIDGE,
}


# ---------------------------------------------------------------------------
# 模块加载与符号表
# ---------------------------------------------------------------------------


class Module:
    def __init__(self, dotted: str) -> None:
        self.dotted = dotted
        path = BACKEND / Path(*dotted.split(".")).with_suffix(".py")
        self.src = path.read_text(encoding="utf-8")
        self.tree = ast.parse(self.src, filename=str(path))
        self.symbols = module_symbols(self.tree)
        self.imports = script_imports(self.tree)
        self.blocks = module_blocks(self.tree)


def load_module(dotted: str, cache: dict[str, Module]) -> Module:
    if dotted not in cache:
        cache[dotted] = Module(dotted)
    return cache[dotted]


def module_symbols(tree: ast.Module) -> dict[str, ast.stmt]:
    out: dict[str, ast.stmt] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[node.name] = node
        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            out[node.targets[0].id] = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out[node.target.id] = node
    return out


def script_imports(tree: ast.Module) -> dict[str, tuple[str, str]]:
    """本地名 -> (模块, 原名)，收录全模块（含函数内）的 script.* from-import。"""
    out: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("script."):
            for a in node.names:
                out[a.asname or a.name] = (node.module, a.name)
    return out


def _is_main_guard(node: ast.If) -> bool:
    test = node.test
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
    )


def module_blocks(tree: ast.Module) -> list[ast.stmt]:
    """模块级可执行块（For/If/With/Try/Assert/非 docstring Expr）——伪符号载体。"""
    out: list[ast.stmt] = []
    for i, node in enumerate(tree.body):
        if isinstance(node, ast.If) and _is_main_guard(node):
            continue
        if isinstance(
            node, (ast.For, ast.AsyncFor, ast.If, ast.With, ast.AsyncWith, ast.Try, ast.Assert)
        ):
            out.append(node)
        elif isinstance(node, ast.Expr) and not (
            i == 0 and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
        ):
            out.append(node)
    return out


def names_used(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            base = n
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name):
                out.add(base.id)
    return out


def bound_names(node: ast.AST) -> set[str]:
    """块内绑定的名字（Assign 目标 / for 目标 / with 目标等）。"""
    out: set[str] = set()
    for n in ast.walk(node):
        targets: list[ast.expr] = []
        if isinstance(n, (ast.Assign, ast.AnnAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
        elif isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
            targets = [n.target]
        elif isinstance(n, (ast.With, ast.AsyncWith)):
            targets = [item.optional_vars for item in n.items if item.optional_vars]
        for t in targets:
            for el in ast.walk(t):
                if isinstance(el, ast.Name):
                    out.add(el.id)
                elif isinstance(el, ast.Starred) and isinstance(el.value, ast.Name):
                    out.add(el.value.id)
    return out


# ---------------------------------------------------------------------------
# 源码段
# ---------------------------------------------------------------------------


def segment_with_decorators(src: str, node: ast.stmt) -> str:
    lines = src.splitlines(keepends=True)
    start = node.lineno - 1
    for d in getattr(node, "decorator_list", []) or []:
        start = min(start, d.lineno - 1)
    return "".join(lines[start : node.end_lineno])


def strip_local_banned_imports(seg: str) -> str:
    """删除段内函数局部的 banned import 行（内联后符号已在模块层）。"""
    try:
        tree = ast.parse(seg)
    except SyntaxError:
        return seg
    drops: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.ImportFrom, ast.Import)) or node.col_offset == 0:
            continue  # 只处理函数体内（有缩进）的 import
        if isinstance(node, ast.ImportFrom):
            banned = (node.module or "").startswith(BANNED_PREFIXES)
        else:
            banned = all(a.name.startswith(BANNED_TOPLEVEL) for a in node.names)
        if banned:
            drops.append((node.lineno, node.end_lineno or node.lineno))
    if not drops:
        return seg
    lines = seg.splitlines(keepends=True)
    drop_set: set[int] = set()
    for lo, hi in drops:
        drop_set.update(range(lo - 1, hi))
    kept = [line for i, line in enumerate(lines) if i not in drop_set]
    return "".join(kept)


def transform_segment(seg: str) -> str:
    seg = strip_local_banned_imports(seg)
    for old, new in TYPE_DEMOTION.items():
        seg = re.sub(rf"\b{old}\b", new, seg)
    seg = seg.replace("except GraphRequestError", "except Exception")
    # GraphRequestError 泛化为 Exception 后，专属的 exc.body 属性访问需兜底
    seg = re.sub(r"\bexc\.body\b", 'getattr(exc, "body", "")', seg)
    return seg.rstrip() + "\n"


def collect_import_lines(tree: ast.Module) -> list[str]:
    """模块头白名单 import（stdlib/第三方），banned 与 __future__ 除外。"""
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            mod = node.module or ""
            if mod == "__future__" or mod.startswith(BANNED_PREFIXES):
                continue
            names = ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in node.names)
            out.append(f"from {mod} import {names}")
        elif isinstance(node, ast.Import):
            keep = [a for a in node.names if not a.name.startswith(BANNED_TOPLEVEL)]
            if keep:
                names = ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in keep)
                out.append(f"import {names}")
    return out


# ---------------------------------------------------------------------------
# 闭包
# ---------------------------------------------------------------------------


class Closure:
    """(mod, sym) -> (段, 依赖)；sym 以 "@block:行号" 表示模块级可执行块。"""

    def __init__(self) -> None:
        self.srcs: dict[tuple[str, str], str] = {}
        self.deps: dict[tuple[str, str], set[tuple[str, str]]] = {}
        self.import_lines: list[str] = []
        self.by_name: dict[str, set[tuple[str, str]]] = {}

    def add(self, key: tuple[str, str], seg: str, deps: set[tuple[str, str]]) -> None:
        if key in self.srcs:
            return
        self.srcs[key] = seg
        self.deps[key] = deps
        name = key[1]
        if not name.startswith("@block:"):
            self.by_name.setdefault(name, set()).add(key)


def expand_closure(entries: list[tuple[str, str]], cache: dict[str, Module]) -> Closure:
    closure = Closure()
    queue = list(entries)
    seen: set[tuple[str, str]] = set()
    while queue:
        mod_dotted, sym = queue.pop()
        if (mod_dotted, sym) in seen:
            continue
        seen.add((mod_dotted, sym))
        try:
            mod = load_module(mod_dotted, cache)
        except FileNotFoundError:
            continue  # 非文件模块（如 package.__init__），跳过
        if sym.startswith("@block:"):
            lineno = int(sym.split(":", 1)[1])
            node = next(b for b in mod.blocks if b.lineno == lineno)
            used = names_used(node)
            # 读到的本模块符号 + 块会写到的本模块符号（catalog 的 for 填充
            # SPECS_BY_KEY）：写目标依赖其初始化语句，保证「先 init 后填充」
            # 的顺序与访问时序无关
            deps = {(mod_dotted, u) for u in used | bound_names(node) if u in mod.symbols}
            deps.discard((mod_dotted, sym))
            closure.add((mod_dotted, sym), segment_with_decorators(mod.src, node), deps)
            queue.extend(deps)
        else:
            if sym not in mod.symbols:
                continue
            node = mod.symbols[sym]
            used = names_used(node)
            deps: set[tuple[str, str]] = set()
            for u in used:
                if u in mod.symbols and u != sym:
                    deps.add((mod_dotted, u))
                elif u in mod.imports:
                    target_mod, target_sym = mod.imports[u]
                    if (
                        BACKEND / Path(*f"{target_mod}.{target_sym}".split(".")).with_suffix(".py")
                    ).exists():
                        # 闭包模块间出现 from pkg import submodule：语义需人工确认
                        raise RuntimeError(
                            f"{mod_dotted} 通过 from-import 引用了子模块 {target_mod}.{target_sym}"
                        )
                    deps.add((target_mod, target_sym))
            closure.add((mod_dotted, sym), segment_with_decorators(mod.src, node), deps)
            queue.extend(deps)
        for line in collect_import_lines(mod.tree):
            if line not in closure.import_lines:
                closure.import_lines.append(line)
        # 该模块的可执行块全部入队（catalog for 循环填充 SPECS_BY_KEY 等）
        for block in mod.blocks:
            key = (mod_dotted, f"@block:{block.lineno}")
            if key not in seen:
                queue.append(key)
    return closure


def topo_order(closure: Closure, entry: tuple[str, str] | None) -> list[tuple[str, str]]:
    keys = list(closure.srcs)
    order: list[tuple[str, str]] = []
    visited: set[tuple[str, str]] = set()
    temp: set[tuple[str, str]] = set()

    def visit(key: tuple[str, str]) -> None:
        if key in visited or key not in closure.srcs:
            return
        if key in temp:
            return  # 函数体延迟求值，模块级互调允许环
        temp.add(key)
        for dep in sorted(closure.deps.get(key, set())):
            visit(dep)
        temp.discard(key)
        visited.add(key)
        order.append(key)

    for key in keys:
        if key != entry:
            visit(key)
    if entry:
        visit(entry)
    return order


def render_closure(closure: Closure, entry: tuple[str, str] | None, label: str) -> list[str]:
    # 各模块的模块级 logger 同名同构（logging.getLogger），合并为单条脚本级
    # logger；非该模式的同名冲突仍然拦截
    for key in list(closure.by_name.get("logger", set())):
        if not re.match(r"logger\s*=\s*logging\.getLogger", closure.srcs[key]):
            raise RuntimeError(f"logger 符号不是 getLogger 赋值，需人工处理: {key}")
        closure.srcs.pop(key)
        closure.deps.pop(key)
    closure.by_name.pop("logger", None)
    conflicts = {n: keys for n, keys in closure.by_name.items() if len(keys) > 1}
    if conflicts:
        raise RuntimeError(
            f"同名符号跨模块冲突，需人工处理: { {n: sorted(map(str, k)) for n, k in conflicts.items()} }"
        )
    segs: list[str] = []
    emitted: set[str] = set()
    for key in topo_order(closure, entry):
        _, sym = key
        if sym in BRIDGES:
            seg = BRIDGES[sym]
        else:
            seg = transform_segment(closure.srcs[key])
        if sym in emitted:  # 同名去重（冲突已在上面拦下，此处只兜底）
            continue
        if not sym.startswith("@block:"):
            emitted.add(sym)
        segs.append(seg.rstrip())
    # 桥兜底：段里引用了桥名但闭包没收录该符号（如 private_state_dir 来自
    # utils.*，非 script.* 的依赖追踪覆盖不到）时，补平台注入版定义
    for bridge_name in list(BRIDGES):
        if bridge_name in closure.by_name:
            continue
        if any(re.search(rf"\b{bridge_name}\s*\(", s) for s in segs):
            segs.append(BRIDGES[bridge_name].rstrip())
    if any(re.search(r"\blogger\b", s) for s in segs):
        segs.insert(0, f'logger = logging.getLogger("{label}")')
    return segs


# ---------------------------------------------------------------------------
# 产物组装
# ---------------------------------------------------------------------------


def find_legacy_module(tree: ast.Module) -> str | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("script."):
            for a in node.names:
                cand = f"{node.module}.{a.name}"
                if (BACKEND / Path(*cand.split(".")).with_suffix(".py")).exists():
                    return cand
    return None


def existing_step_id(tree: ast.Module) -> str | None:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "step"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            return node.args[0].value
    return None


def step_id_for(filename: str) -> str:
    name = filename
    for suffix in ("_relation_step.py", "_entity_step.py", "_relation.py", "_step.py", ".py"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name


def merge_import_lines(lines: list[str]) -> list[str]:
    """按模块合并 import 行：多模块收集时同名重复导入（如 ``from typing import Any``
    与 ``from typing import Any, Mapping`` 并存）会触发 F811，运行前就得拦干净。"""
    from_order: list[str] = []
    from_map: dict[str, list[str]] = {}
    plain: list[str] = []
    plain_seen: set[str] = set()
    for line in lines:
        m = re.match(r"from ([\w.]+) import (.+)", line)
        if m:
            mod = m.group(1)
            names = from_map.setdefault(mod, [])
            if mod not in from_order:
                from_order.append(mod)
            for name in (n.strip() for n in m.group(2).split(",")):
                if name not in names:
                    names.append(name)
        elif line.startswith("import ") and line not in plain_seen:
            plain_seen.add(line)
            plain.append(line)
    return plain + [f"from {mod} import {', '.join(from_map[mod])}" for mod in from_order]


def assemble(doc: str, import_lines: list[str], segs: list[str], entry: str) -> str:
    header = [
        "from __future__ import annotations",
        *merge_import_lines([ln for ln in import_lines if ln != "from kg_sdk import step"]),
        "from kg_sdk import step",
    ]
    seen: set[str] = set()
    header = [line for line in header if not (line in seen or seen.add(line))]
    body = "\n\n\n".join(seg for seg in segs if seg.strip())
    parts = [doc.rstrip(), "\n".join(header), body, entry]
    return "\n\n\n".join(p for p in parts if p.strip()) + "\n"


def build(adaptor: Path, cache: dict[str, Module]) -> str:
    """薄适配层 → 自包含：legacy transform 闭包内联 + @step 入口。"""
    src = adaptor.read_text(encoding="utf-8")
    tree = ast.parse(src)
    legacy = find_legacy_module(tree)
    if legacy is None:
        raise RuntimeError("非薄适配层（无 script.* 模块导入），应走 build_self")
    entry_mod = load_module(legacy, cache)
    if "transform" not in entry_mod.symbols:
        raise RuntimeError(f"{legacy} 无 transform 入口")
    closure = expand_closure([(legacy, "transform")], cache)
    # 平台上传门禁（service/script_steps._LEGACY_ENTRIES）：@step 与旧入口名
    # transform 不能并存——内联的 legacy transform 改名 _transform
    key = (legacy, "transform")
    closure.srcs[key] = closure.srcs[key].replace("def transform(", "def _transform(", 1)
    sid = existing_step_id(tree) or step_id_for(adaptor.name)
    doc = (
        f'"""{sid} 抽取步（自包含单文件，平台喂数管道 kg.schema.extract 直传可用）。\n\n'
        f"由 script/tools/build_portable_steps.py 从 ``{legacy}`` 及其依赖闭包自动生成；\n"
        "抽取口径与老脚本逐行一致，MySQL/图客户端改经平台 ctx 注入。请勿手改，\n"
        '改动请落到原模块后重新生成。\n"""'
    )
    entry = f'@step("{sid}")\ndef emit(payload):\n    return _transform(payload)'
    return assemble(
        doc, closure.import_lines, render_closure(closure, (legacy, "transform"), sid), entry
    )


def build_self(adaptor: Path, cache: dict[str, Module]) -> str:
    """自研脚本：本体保留，内联其 script.* 导入符号并清洗。"""
    src = adaptor.read_text(encoding="utf-8")
    tree = ast.parse(src)
    own = module_symbols(tree)
    doc = ""
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
    ):
        doc = segment_with_decorators(src, tree.body[0]).rstrip()
    # 需要内联的外部符号：script.* 导入且本文件未自定义
    entries: list[tuple[str, str]] = []
    for local, (mod_dotted, orig) in script_imports(tree).items():
        if local in own:
            continue
        entries.append(
            (f"{mod_dotted}.{orig}", "transform")
            if (BACKEND / Path(*f"{mod_dotted}.{orig}".split(".")).with_suffix(".py")).exists()
            else (mod_dotted, orig)
        )
    closure = expand_closure(entries, cache)
    segs = render_closure(closure, entries[-1] if entries else None, step_id_for(adaptor.name))
    sid = existing_step_id(tree) or step_id_for(adaptor.name)
    # 本体（去掉 import 行，保留 @step 入口与常量；局部 banned import 剔除）
    body_parts: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and node is tree.body[0]
        ):
            continue
        seg = transform_segment(segment_with_decorators(src, node))
        if isinstance(node, ast.FunctionDef) and existing_step_id(tree) is None:
            # 裸 @step 补显式 id（任务详情抽屉步名展示用）。段以装饰器行开头，
            # 不能依赖前导 \n——按行锚定匹配独占一行的裸 @step
            seg = re.sub(r"(?m)^@step$", f'@step("{sid}")', seg)
        body_parts.append(seg.rstrip())
    # 只补闭包未覆盖且真正被引用的桥
    output_probe = "\n".join(segs + body_parts)
    for bridge_name in list(BRIDGES):
        if bridge_name in closure.by_name:
            continue
        if re.search(rf"\b{bridge_name}\s*\(", output_probe):
            segs.insert(0, BRIDGES[bridge_name].rstrip())
    # 本体 import + 闭包模块的 import（内联符号的依赖也要带上，否则 json/hashlib
    # 等只存在于被内联模块头部的名字会缺 import）
    return assemble(
        doc, collect_import_lines(tree) + closure.import_lines, segs, "\n\n\n".join(body_parts)
    )


# ---------------------------------------------------------------------------
# 校验：产物不得有未定义名 / banned import
# ---------------------------------------------------------------------------


def _scope_binds(node: ast.AST) -> set[str]:
    """函数作用域内绑定的名字（参数/赋值/for/with/except/推导式/嵌套 def）。"""
    binds: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            binds.add(n.name)
        elif isinstance(n, ast.Lambda):
            for a in n.args.args + n.args.posonlyargs + n.args.kwonlyargs:
                binds.add(a.arg)
            if n.args.vararg:
                binds.add(n.args.vararg.arg)
            if n.args.kwarg:
                binds.add(n.args.kwarg.arg)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            binds.add(n.id)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            binds.add(n.name)
        elif isinstance(n, ast.arg):
            binds.add(n.arg)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                binds.add(a.asname or a.name.split(".")[0])
        elif isinstance(n, ast.Global) or isinstance(n, ast.Nonlocal):
            binds.update(n.names)
    return binds


def verify_file(path: Path) -> list[str]:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    problems: list[str] = []
    for lineno, line in enumerate(src.splitlines(), 1):
        if re.search(r"\b(?:from|import)\s+(script|infra|utils)\b", line):
            problems.append(f"{path.name}:{lineno}: banned import 残留: {line.strip()}")
    module_names: set[str] = set(dir(builtins)) | {"__name__", "__file__"}
    for node in tree.body:
        module_names |= bound_names(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            module_names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                module_names.add(a.asname or a.name.split(".")[0])
    scopes: list[tuple[set[str], ast.AST]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            scopes.append((module_names | _scope_binds(node), node))
    ok = True
    while ok:
        ok = False
        for scope_names, node in list(scopes):
            for n in ast.walk(node):
                if (
                    isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef))
                    and n is not node
                ):
                    if not any(n is sub for _, sub in scopes):
                        scopes.append((scope_names | _scope_binds(n), n))
                        ok = True
    for scope_names, node in scopes:
        if isinstance(node, ast.ClassDef):
            class_binds = set()
            for stmt in node.body:
                class_binds |= bound_names(stmt)
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    class_binds.add(stmt.name)
            scope_names = scope_names | class_binds
        for n in ast.walk(node):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in scope_names:
                problems.append(f"{path.name}:{n.lineno}: 未定义名 {n.id}")
    return problems


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只构建不写回")
    ap.add_argument(
        "--verify", action="store_true", help="校验磁盘上的产物（未定义名/banned import）"
    )
    ap.add_argument("files", nargs="*", help="指定文件名（缺省全量）")
    args = ap.parse_args()
    if args.verify:
        targets = (
            [RESTORE_DIR / f for f in args.files]
            if args.files
            else sorted(RESTORE_DIR.glob("*.py"))
        )
        problems = [p for f in targets if f.name != "__init__.py" for p in verify_file(f)]
        print("\n".join(problems) if problems else "校验通过：无未定义名 / banned import")
        sys.exit(1 if problems else 0)
    targets = (
        [RESTORE_DIR / f for f in args.files] if args.files else sorted(RESTORE_DIR.glob("*.py"))
    )
    cache: dict[str, Module] = {}
    ok = bad = 0
    for f in targets:
        if f.name == "__init__.py":
            continue
        try:
            if f.name in SELF_FILES:
                src_new = build_self(f, cache)
            else:
                src_new = build(f, cache)
            if args.check:
                print(f"{f.name:44s} check ok  ({src_new.count(chr(10))} 行)")
            else:
                f.write_text(src_new, encoding="utf-8")
                print(f"{f.name:44s} 写回 ({src_new.count(chr(10))} 行)")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"{f.name:44s} FAIL: {exc}")
            bad += 1
    print(f"\n完成: ok={ok} bad={bad}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
