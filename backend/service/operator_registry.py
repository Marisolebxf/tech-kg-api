"""线程安全、可持久化且支持热更新的 Python 算子注册表。"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import os
import re
import sys
import threading
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import ModuleType
from typing import Any

from infra.operator_store import (
    OperatorStoreError,
    S3OperatorStore,
    create_operator_store_from_env,
)
from service.operator_builtins import (
    data_normalize,
    entity_extract,
    entity_load,
    relation_extract,
    relation_load,
)

DEFAULT_OPERATOR_TIMESTAMP = "2026-01-01T00:00:00+00:00"

logger = logging.getLogger(__name__)

JsonObject = dict[str, Any]
OperatorCallable = Callable[[list[JsonObject], JsonObject], list[JsonObject]]
OPERATOR_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{0,127}$")


class OperatorKind(StrEnum):
    DATA_PROCESSING = "data_processing"
    ENTITY_EXTRACTION = "entity_extraction"
    RELATION_EXTRACTION = "relation_extraction"
    ENTITY_INGESTION = "entity_ingestion"
    RELATION_INGESTION = "relation_ingestion"


class OperatorRegistryError(Exception):
    """注册表可预期错误。"""


class OperatorNotFoundError(OperatorRegistryError):
    pass


class OperatorConflictError(OperatorRegistryError):
    pass


class OperatorValidationError(OperatorRegistryError):
    pass


class OperatorExecutionError(OperatorRegistryError):
    pass


class OperatorStorageError(OperatorRegistryError):
    pass


@dataclass(frozen=True, slots=True)
class OperatorManifest:
    name: str
    version: str
    kind: OperatorKind
    description: str
    builtin: bool
    updated_at: str

    def to_dict(self) -> JsonObject:
        value = asdict(self)
        value["kind"] = self.kind.value
        return value


@dataclass(frozen=True, slots=True)
class RegisteredOperator:
    function: OperatorCallable
    manifest: OperatorManifest


BUILTIN_OPERATORS: tuple[tuple[OperatorManifest, OperatorCallable], ...] = (
    (
        OperatorManifest(
            name="builtin.data_normalize",
            version="1.0.0",
            kind=OperatorKind.DATA_PROCESSING,
            description="字符串清洗、字段映射和空值过滤",
            builtin=True,
            updated_at=DEFAULT_OPERATOR_TIMESTAMP,
        ),
        data_normalize,
    ),
    (
        OperatorManifest(
            name="builtin.entity_extract",
            version="1.0.0",
            kind=OperatorKind.ENTITY_EXTRACTION,
            description="基于正则规则的实体抽取",
            builtin=True,
            updated_at=DEFAULT_OPERATOR_TIMESTAMP,
        ),
        entity_extract,
    ),
    (
        OperatorManifest(
            name="builtin.relation_extract",
            version="1.0.0",
            kind=OperatorKind.RELATION_EXTRACTION,
            description="基于字段映射或正则规则的关系抽取",
            builtin=True,
            updated_at=DEFAULT_OPERATOR_TIMESTAMP,
        ),
        relation_extract,
    ),
    (
        OperatorManifest(
            name="builtin.entity_load",
            version="1.0.0",
            kind=OperatorKind.ENTITY_INGESTION,
            description="基于主键和名称匹配的实体入库计划",
            builtin=True,
            updated_at=DEFAULT_OPERATOR_TIMESTAMP,
        ),
        entity_load,
    ),
    (
        OperatorManifest(
            name="builtin.relation_load",
            version="1.0.0",
            kind=OperatorKind.RELATION_INGESTION,
            description="基于关系组合键匹配的关系入库计划",
            builtin=True,
            updated_at=DEFAULT_OPERATOR_TIMESTAMP,
        ),
        relation_load,
    ),
)


class OperatorRegistry:
    """保存算子元数据和可调用对象，并在调用时解析最新实现。"""

    def __init__(
        self,
        operator_dir: str | Path,
        watch_interval: float = 0.25,
        store: S3OperatorStore | None = None,
    ) -> None:
        self.operator_dir = Path(operator_dir)
        self.operator_dir.mkdir(parents=True, exist_ok=True)
        self.watch_interval = watch_interval
        self.store = store
        self._lock = threading.RLock()
        self._operators: dict[str, RegisteredOperator] = {}
        self._file_snapshot: dict[str, tuple[int, int, str]] = {}
        self._stop_event = threading.Event()
        self._watcher: threading.Thread | None = None
        self._register_builtins()
        self.reload_all()

    def _register_builtins(self) -> None:
        with self._lock:
            for manifest, function in BUILTIN_OPERATORS:
                self._operators[manifest.name] = RegisteredOperator(function, manifest)

    @property
    def reserved_names(self) -> set[str]:
        return {manifest.name for manifest, _ in BUILTIN_OPERATORS}

    @property
    def has_shared_store(self) -> bool:
        return self.store is not None

    def initialize_store(self) -> list[str]:
        """服务启动时创建 bucket，并把 RustFS/S3 真源同步到本地缓存。"""
        if self.store is None:
            return self.reload_all()
        try:
            self.store.ensure_ready()
            return self.sync_from_store()
        except OperatorStoreError as exc:
            raise OperatorStorageError(str(exc)) from exc

    def sync_from_store(self) -> list[str]:
        if self.store is None:
            return self.reload_all()
        try:
            bundles = self.store.list_bundles()
        except OperatorStoreError as exc:
            raise OperatorStorageError(str(exc)) from exc
        return self._install_bundles(bundles, replace=True, persist=False)

    def start_watcher(self) -> None:
        with self._lock:
            if self._watcher and self._watcher.is_alive():
                return
            self._stop_event.clear()
            self._watcher = threading.Thread(
                target=self._watch_loop,
                name="operator-registry-watcher",
                daemon=True,
            )
            self._watcher.start()

    def stop_watcher(self) -> None:
        self._stop_event.set()
        watcher = self._watcher
        if watcher and watcher.is_alive():
            watcher.join(timeout=max(1.0, self.watch_interval * 4))
        self._watcher = None

    def _watch_loop(self) -> None:
        while not self._stop_event.wait(self.watch_interval):
            try:
                self.refresh_if_changed()
            except Exception:  # pragma: no cover - watcher must remain alive
                logger.exception("算子文件监听失败")

    def _snapshot(self) -> dict[str, tuple[int, int, str]]:
        snapshot: dict[str, tuple[int, int, str]] = {}
        for path in self.operator_dir.iterdir():
            if path.is_file() and path.suffix in {".py", ".json"}:
                stat = path.stat()
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                snapshot[path.name] = (stat.st_mtime_ns, stat.st_size, digest)
        return snapshot

    def refresh_if_changed(self) -> bool:
        current = self._snapshot()
        with self._lock:
            changed = current != self._file_snapshot
        if changed:
            self.reload_all()
        return changed

    def reload_all(self) -> list[str]:
        """重载所有用户算子；单个文件损坏时保留该算子的上一版本。"""
        loaded: list[str] = []
        discovered_names: set[str] = set()
        for manifest_path in sorted(self.operator_dir.glob("*.json")):
            discovered_names.add(manifest_path.stem)
            source_path = manifest_path.with_suffix(".py")
            if not source_path.exists():
                logger.warning("算子 %s 缺少 Python 源文件", manifest_path.stem)
                continue
            try:
                manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest = self._manifest_from_dict(manifest_data)
                if manifest.name != manifest_path.stem:
                    raise OperatorValidationError("清单 name 必须与文件名一致")
                self._validate_user_manifest(manifest)
                function = self._load_function(source_path, manifest.name)
            except Exception as exc:
                logger.warning("重载算子 %s 失败，继续使用上一版本: %s", manifest_path.stem, exc)
                continue
            with self._lock:
                self._operators[manifest.name] = RegisteredOperator(function, manifest)
            loaded.append(manifest.name)

        with self._lock:
            stale_names = {
                name
                for name, registered in self._operators.items()
                if not registered.manifest.builtin and name not in discovered_names
            }
            for name in stale_names:
                self._operators.pop(name, None)
            self._file_snapshot = self._snapshot()
        return loaded

    def reload(self, name: str) -> OperatorManifest:
        self._validate_name(name)
        manifest_path = self.operator_dir / f"{name}.json"
        source_path = self.operator_dir / f"{name}.py"
        if not manifest_path.exists() or not source_path.exists():
            raise OperatorNotFoundError(f"算子不存在: {name}")
        manifest = self._manifest_from_dict(json.loads(manifest_path.read_text(encoding="utf-8")))
        if manifest.name != name:
            raise OperatorValidationError("清单 name 必须与请求的算子名称一致")
        self._validate_user_manifest(manifest)
        function = self._load_function(source_path, name)
        with self._lock:
            self._operators[name] = RegisteredOperator(function, manifest)
            self._file_snapshot = self._snapshot()
        return manifest

    def create(
        self,
        *,
        name: str,
        version: str,
        kind: OperatorKind,
        source: str,
        description: str = "",
    ) -> OperatorManifest:
        self._validate_name(name)
        if name in self.reserved_names:
            raise OperatorConflictError(f"内置算子名称不可覆盖: {name}")
        if self._operator_exists(name):
            raise OperatorConflictError(f"算子已存在: {name}")
        return self._write_and_reload(name, version, kind, source, description)

    def update(
        self,
        *,
        name: str,
        version: str,
        kind: OperatorKind,
        source: str,
        description: str = "",
    ) -> OperatorManifest:
        self._validate_name(name)
        if name in self.reserved_names:
            raise OperatorConflictError(f"内置算子不可修改: {name}")
        if not self._operator_exists(name):
            raise OperatorNotFoundError(f"算子不存在: {name}")
        return self._write_and_reload(name, version, kind, source, description)

    def _write_and_reload(
        self,
        name: str,
        version: str,
        kind: OperatorKind,
        source: str,
        description: str,
    ) -> OperatorManifest:
        if not version.strip():
            raise OperatorValidationError("version 不能为空")
        self._validate_source(source, name)
        manifest = OperatorManifest(
            name=name,
            version=version.strip(),
            kind=kind,
            description=description.strip(),
            builtin=False,
            updated_at=datetime.now(UTC).isoformat(),
        )
        bundle = {"manifest": manifest.to_dict(), "source": source}
        if self.store is not None:
            try:
                self.store.put(name, bundle)
            except OperatorStoreError as exc:
                raise OperatorStorageError(str(exc)) from exc
        self._atomic_write(self.operator_dir / f"{name}.py", source)
        self._atomic_write(
            self.operator_dir / f"{name}.json",
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2) + "\n",
        )
        return self.reload(name)

    def _operator_exists(self, name: str) -> bool:
        if (self.operator_dir / f"{name}.json").exists():
            return True
        if self.store is None:
            return False
        try:
            return self.store.exists(name)
        except OperatorStoreError as exc:
            raise OperatorStorageError(str(exc)) from exc

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)

    def delete(self, name: str) -> None:
        self._validate_name(name)
        if name in self.reserved_names:
            raise OperatorConflictError(f"内置算子不可删除: {name}")
        paths = [self.operator_dir / f"{name}.py", self.operator_dir / f"{name}.json"]
        exists = any(path.exists() for path in paths)
        if self.store is not None:
            try:
                exists = exists or self.store.exists(name)
            except OperatorStoreError as exc:
                raise OperatorStorageError(str(exc)) from exc
        if not exists:
            raise OperatorNotFoundError(f"算子不存在: {name}")
        if self.store is not None:
            try:
                self.store.delete(name)
            except OperatorStoreError as exc:
                raise OperatorStorageError(str(exc)) from exc
        for path in paths:
            path.unlink(missing_ok=True)
        with self._lock:
            self._operators.pop(name, None)
            self._file_snapshot = self._snapshot()

    def export_user_operators(self) -> list[JsonObject]:
        """导出源码和清单，供不共享文件系统的 worker 同步。"""
        bundles: list[JsonObject] = []
        for manifest in self.list():
            if manifest.builtin:
                continue
            source_path = self.operator_dir / f"{manifest.name}.py"
            if source_path.exists():
                bundles.append(
                    {
                        "manifest": manifest.to_dict(),
                        "source": source_path.read_text(encoding="utf-8"),
                    }
                )
        return bundles

    def sync_user_operators(self, bundles: list[JsonObject], *, replace: bool = True) -> list[str]:
        """校验并安装控制面下发的算子快照；本地模式用于兼容无 S3 worker。"""
        return self._install_bundles(bundles, replace=replace, persist=True)

    def _install_bundles(
        self,
        bundles: list[JsonObject],
        *,
        replace: bool,
        persist: bool,
    ) -> list[str]:
        validated: list[tuple[OperatorManifest, str]] = []
        for bundle in bundles:
            manifest_value = bundle.get("manifest")
            source = bundle.get("source")
            if not isinstance(manifest_value, dict) or not isinstance(source, str):
                raise OperatorValidationError("算子同步包必须包含 manifest 和 source")
            manifest = self._manifest_from_dict(manifest_value)
            self._validate_user_manifest(manifest)
            self._validate_source(source, manifest.name)
            validated.append((manifest, source))

        incoming_names = {manifest.name for manifest, _ in validated}
        for manifest, source in validated:
            if persist and self.store is not None:
                try:
                    self.store.put(
                        manifest.name,
                        {"manifest": manifest.to_dict(), "source": source},
                    )
                except OperatorStoreError as exc:
                    raise OperatorStorageError(str(exc)) from exc
            self._atomic_write(self.operator_dir / f"{manifest.name}.py", source)
            self._atomic_write(
                self.operator_dir / f"{manifest.name}.json",
                json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2) + "\n",
            )

        if replace:
            current_user_names = {manifest.name for manifest in self.list() if not manifest.builtin}
            for stale_name in current_user_names - incoming_names:
                if persist and self.store is not None:
                    try:
                        self.store.delete(stale_name)
                    except OperatorStoreError as exc:
                        raise OperatorStorageError(str(exc)) from exc
                (self.operator_dir / f"{stale_name}.py").unlink(missing_ok=True)
                (self.operator_dir / f"{stale_name}.json").unlink(missing_ok=True)
        return self.reload_all()

    def list(self, kind: OperatorKind | None = None) -> list[OperatorManifest]:
        self.refresh_if_changed()
        with self._lock:
            manifests = [item.manifest for item in self._operators.values()]
        if kind is not None:
            manifests = [manifest for manifest in manifests if manifest.kind == kind]
        return sorted(manifests, key=lambda manifest: manifest.name)

    def get(self, name: str) -> OperatorManifest:
        self.refresh_if_changed()
        with self._lock:
            registered = self._operators.get(name)
        if registered is None:
            raise OperatorNotFoundError(f"算子不存在: {name}")
        return registered.manifest

    async def invoke(
        self, name: str, data: list[JsonObject], ctx: JsonObject | None = None
    ) -> list[JsonObject]:
        """在执行时查表，因此更新后的下一次调用会解析到新函数。"""
        self.refresh_if_changed()
        with self._lock:
            registered = self._operators.get(name)
        if registered is None:
            raise OperatorNotFoundError(f"算子不存在: {name}")
        safe_data = deepcopy(data)
        safe_ctx = deepcopy(ctx or {})
        try:
            result = await asyncio.to_thread(registered.function, safe_data, safe_ctx)
            if inspect.isawaitable(result):
                result = await result
            self._validate_result(result)
            return result
        except OperatorValidationError as exc:
            raise OperatorExecutionError(str(exc)) from exc
        except Exception as exc:
            raise OperatorExecutionError(f"算子 {name} 执行失败: {exc}") from exc

    @staticmethod
    def _validate_result(result: Any) -> None:
        if not isinstance(result, list) or any(not isinstance(item, dict) for item in result):
            raise OperatorValidationError("算子返回值必须是 list[dict]")
        try:
            json.dumps(result, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise OperatorValidationError(f"算子返回值必须可以序列化为 JSON: {exc}") from exc

    @staticmethod
    def _validate_name(name: str) -> None:
        if not OPERATOR_NAME_PATTERN.fullmatch(name):
            raise OperatorValidationError(
                "name 必须以字母开头，且只能包含字母、数字、点、下划线和连字符"
            )

    def _validate_user_manifest(self, manifest: OperatorManifest) -> None:
        self._validate_name(manifest.name)
        if manifest.name in self.reserved_names:
            raise OperatorConflictError(f"内置算子名称不可覆盖: {manifest.name}")
        if manifest.builtin:
            raise OperatorValidationError("用户算子的 builtin 必须为 false")

    def _validate_source(self, source: str, name: str) -> None:
        if len(source.encode("utf-8")) > 256 * 1024:
            raise OperatorValidationError("算子源码不能超过 256 KiB")
        self._function_from_source(source, f"<operator:{name}>", name)

    def _load_function(self, path: Path, name: str) -> OperatorCallable:
        return self._function_from_source(path.read_text(encoding="utf-8"), str(path), name)

    @staticmethod
    def _function_from_source(source: str, filename: str, name: str) -> OperatorCallable:
        module_name = f"user_operators.{name}"
        module = ModuleType(module_name)
        module.__file__ = filename
        try:
            code = compile(source, filename, "exec")
            exec(code, module.__dict__)
        except Exception as exc:
            raise OperatorValidationError(f"Python 源码加载失败: {exc}") from exc
        function = getattr(module, "operator", None)
        if not callable(function):
            raise OperatorValidationError("源码必须定义可调用的顶层函数 operator(data, ctx)")
        try:
            inspect.signature(function).bind([], {})
        except TypeError as exc:
            raise OperatorValidationError("operator 必须可用 operator(data, ctx) 调用") from exc
        sys.modules[module_name] = module
        return function

    @staticmethod
    def _manifest_from_dict(value: JsonObject) -> OperatorManifest:
        try:
            return OperatorManifest(
                name=str(value["name"]),
                version=str(value["version"]),
                kind=OperatorKind(value["kind"]),
                description=str(value.get("description", "")),
                builtin=bool(value.get("builtin", False)),
                updated_at=str(value["updated_at"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise OperatorValidationError(f"算子清单无效: {exc}") from exc


DEFAULT_OPERATOR_DIR = Path(
    os.getenv("OPERATOR_DIR", Path(__file__).resolve().parents[1] / "operators" / "user")
)
REGISTRY = OperatorRegistry(DEFAULT_OPERATOR_DIR, store=create_operator_store_from_env())
