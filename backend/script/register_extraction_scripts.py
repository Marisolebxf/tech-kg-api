"""一次性把单实体/单关系抽取脚本注册为 workflow 定义（category=entity/relation）。

用法（backend 目录）：
    PYTHONPATH=. uv run python -m script.register_extraction_scripts [--host http://localhost:8000]

直接调用本进程的 WorkflowOperationsService（写 techkg_control 库），不经 HTTP；
重复执行幂等（definition id 固定为脚本文件名，save_definition 走 merge）。
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# 非入口的辅助模块，跳过注册
SKIP_FILES = {
    "common.py",
    "mappers.py",
    "org_catalog.py",
    "catalog.py",
    "resolvers.py",
    "org_edges.py",
    "patent_matching.py",
    "__init__.py",
}

ENTITY_DIR = BACKEND_DIR / "script" / "entity_extractors_one_entity"
RELATION_DIR = BACKEND_DIR / "script" / "relation_extractors_one_relation"


def _has_workflow_function(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "workflow"
        for node in ast.walk(tree)
    )


def _definition_id(path: Path) -> str:
    stem = path.stem
    if stem.endswith("_entity"):
        stem = stem[: -len("_entity")]
        prefix = "entity"
    elif stem.endswith("_relation"):
        stem = stem[: -len("_relation")]
        prefix = "relation"
    else:
        prefix = "extract"
    return f"{prefix}-{stem.replace('_', '-')}"


def register(directory: Path, category: str, timeout_seconds: int) -> list[str]:
    from service.workflow_operations import workflow_operations_service

    registered: list[str] = []
    for path in sorted(directory.glob("*.py")):
        if path.name in SKIP_FILES:
            continue
        if not _has_workflow_function(path):
            print(f"跳过（无 workflow 函数）: {path.name}")
            continue
        definition = workflow_operations_service.create_python_definition(
            path.name,
            path.read_bytes(),
            "workflow",
            _definition_id(path),
            path.stem.replace("_entity", "").replace("_relation", "").replace("_", " "),
            timeout_seconds=timeout_seconds,
            category=category,
        )
        registered.append(definition["id"])
        print(f"已注册: {definition['id']} ({category})")
    return registered


def main() -> None:
    parser = argparse.ArgumentParser(description="注册单实体/单关系抽取脚本为 workflow 定义")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=int(__import__("os").getenv("EXTRACT_SCRIPT_TIMEOUT_SECONDS", "3600")),
    )
    args = parser.parse_args()

    entity_ids = register(ENTITY_DIR, "entity", args.timeout_seconds)
    relation_ids = register(RELATION_DIR, "relation", args.timeout_seconds)
    print(f"完成：{len(entity_ids)} 个实体脚本，{len(relation_ids)} 个关系脚本")


if __name__ == "__main__":
    main()
