"""用户抽取脚本 SDK。

activity 在子进程外把"已解析的连接参数"（不是活对象）序列化进 ``KG_SCRIPT_CTX``
环境变量。脚本一律用 ``@step`` 装饰器声明抽取步（单参顶层函数；单步 ``transform``
与顶层 ``STEPS`` 清单已下线），函数内取上下文：

- ``from kg_sdk import current_context``，``ctx = current_context()``
  （未配置时返回 None，脚本降级），直接 ``ctx.mysql`` / ``ctx.graph`` /
  ``ctx.llm`` / ``ctx.semantic`` / ``ctx.config`` ... 取懒构造客户端与增量游标。

未配置某选择器时对应属性返回 ``None``（与 ``infra.llm.get_llm_client`` 降级约定一致），
脚本应判空后再用。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:  # sdk.access：子进程按顶层模块导入（PYTHONPATH 含 backend/sdk），worker/测试按包导入
    from . import access as _access
except ImportError:  # pragma: no cover - 取决于导入方式
    import access as _access

_UNSET = object()


class SemanticToolkitError(RuntimeError):
    """语义计算服务调用失败。"""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 0,
        response: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class SemanticToolkitClient:
    """抽取脚本可直接使用的语义计算小工具客户端。

    ``base_url`` 同时接受服务根地址和以 ``/api/v1`` 结尾的地址，内部会保证
    API 前缀只拼接一次。仅暴露已与接入文档核对一致的接口。
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        *,
        timeout: float = 600.0,
    ) -> None:
        root = base_url.strip().rstrip("/")
        if root.endswith("/api/v1"):
            root = root[: -len("/api/v1")]
        if not root:
            raise ValueError("semantic toolkit base_url 不能为空")
        self._root = root
        self._api = f"{root}/api/v1"
        self._api_key = api_key
        self._timeout = float(timeout)

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        api: bool = True,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        url = (self._api if api else self._root) + path
        headers = {"Accept": "application/json"}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        request = Request(url, data=body, headers=headers, method=method)
        status_code = 0
        raw = b""
        try:
            with urlopen(request, timeout=timeout or self._timeout) as response:  # noqa: S310
                status_code = int(response.status)
                raw = response.read()
        except HTTPError as exc:
            status_code = int(exc.code)
            raw = exc.read()
        except URLError as exc:
            raise SemanticToolkitError(f"语义计算服务不可达：{exc.reason}") from exc
        except TimeoutError as exc:
            raise SemanticToolkitError("语义计算服务请求超时") from exc

        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            preview = raw.decode("utf-8", errors="replace")[:500]
            raise SemanticToolkitError(
                f"语义计算服务返回非 JSON（HTTP {status_code}）",
                status_code=status_code,
                response=preview,
            ) from exc
        if not isinstance(result, dict):
            raise SemanticToolkitError(
                "语义计算服务返回格式错误：顶层必须是 JSON 对象",
                status_code=status_code,
                response=result,
            )
        code = int(result.get("code", 0) or 0)
        if status_code // 100 != 2 or code != 0:
            detail = (
                result.get("detail")
                or (result.get("data") or {}).get("error_summary")
                or result.get("message")
                or result.get("msg")
                or f"HTTP {status_code}"
            )
            raise SemanticToolkitError(
                str(detail),
                status_code=status_code,
                response=result,
            )
        return result

    def health(self) -> dict[str, Any]:
        """检查语义计算服务是否可达。"""
        return self._request("GET", "/health", api=False, timeout=min(self._timeout, 30))

    def catalog(self) -> dict[str, Any]:
        """返回服务当前公开的功能点目录。"""
        return self._request("GET", "/catalog")

    def general_entities(
        self,
        document_title: str,
        text: str,
        **params: Any,
    ) -> dict[str, Any]:
        """通用实体识别：抽取 PERSON/LOCATION/ORGANIZATION/EVENT。"""
        return self._request(
            "POST",
            "/ner/general/text",
            {"document_title": document_title, "text": text, **params},
        )

    def research_entities(
        self,
        document_title: str,
        text: str,
        **params: Any,
    ) -> dict[str, Any]:
        """科研实体识别：抽取 METHOD/DATASET/INSTRUMENT/THEORY/TOPIC。"""
        return self._request(
            "POST",
            "/ner/research/text",
            {"document_title": document_title, "text": text, **params},
        )

    def domain_entities(
        self,
        document_title: str,
        text: str,
        *,
        domain: str = "",
        **params: Any,
    ) -> dict[str, Any]:
        """专业领域实体识别；未指定领域时由服务自动识别。"""
        payload = {"document_title": document_title, "text": text, **params}
        if domain:
            payload["domain"] = domain
        return self._request("POST", "/ner/domain/text", payload)

    def classify_zh(
        self,
        document_title: str,
        text: str,
        **params: Any,
    ) -> dict[str, Any]:
        """中文科技文献自动分类。"""
        return self._request(
            "POST",
            "/classify/clc/zh/text",
            {"document_title": document_title, "text": text, **params},
        )

    def classify_en(
        self,
        document_title: str,
        text: str,
        **params: Any,
    ) -> dict[str, Any]:
        """英文科技文献自动分类。"""
        return self._request(
            "POST",
            "/classify/clc/en/text",
            {"document_title": document_title, "text": text, **params},
        )

    def classify_domain(
        self,
        document_title: str,
        text: str,
        *,
        domain: str,
        **params: Any,
    ) -> dict[str, Any]:
        """专业领域科技文献分类。"""
        return self._request(
            "POST",
            "/classify/domain/text",
            {
                "document_title": document_title,
                "text": text,
                "domain": domain,
                **params,
            },
        )

    def keywords_zh(
        self,
        document_title: str,
        text: str,
        **params: Any,
    ) -> dict[str, Any]:
        """中文科技文献关键词识别。"""
        return self._request(
            "POST",
            "/keywords/zh/text",
            {"document_title": document_title, "text": text, **params},
        )

    def keywords_en(
        self,
        document_title: str,
        text: str,
        **params: Any,
    ) -> dict[str, Any]:
        """英文科技文献关键词识别。"""
        return self._request(
            "POST",
            "/keywords/en/text",
            {"document_title": document_title, "text": text, **params},
        )

    def concept_definitions(self, text: str, **params: Any) -> dict[str, Any]:
        """从正文中识别概念及其定义。"""
        return self._request("POST", "/concept-definition/text", {"text": text, **params})

    def research_questions(
        self,
        document_title: str,
        text: str,
        **params: Any,
    ) -> dict[str, Any]:
        """识别研究问题句、问题短语和结构化研究问题。"""
        return self._request(
            "POST",
            "/research-question/text",
            {"document_title": document_title, "text": text, **params},
        )

    def moves_zh(
        self,
        document_title: str,
        abstract: str,
        **params: Any,
    ) -> dict[str, Any]:
        """中文摘要语步识别。"""
        return self._request(
            "POST",
            "/move/abstract/zh/text",
            {"document_title": document_title, "text": abstract, **params},
        )

    def moves_en(
        self,
        document_title: str,
        abstract: str,
        **params: Any,
    ) -> dict[str, Any]:
        """英文摘要语步识别。"""
        return self._request(
            "POST",
            "/move/abstract/en/text",
            {"document_title": document_title, "text": abstract, **params},
        )

    def fund_moves(
        self,
        project_name: str,
        full_text: str,
        **params: Any,
    ) -> dict[str, Any]:
        """基金申请书、进展报告或结题报告语步识别。"""
        return self._request(
            "POST",
            "/move/fund/zh/text",
            {"project_name": project_name, "text": full_text, **params},
        )

    def citation_intent(
        self,
        document_title: str,
        full_text: str,
        *,
        reference_entries: str = "",
        **params: Any,
    ) -> dict[str, Any]:
        """识别论文引用句的引用意图。"""
        payload = {
            "document_title": document_title,
            "scientific_document_full_text": full_text,
            **params,
        }
        if reference_entries:
            payload["reference_entries"] = reference_entries
        return self._request("POST", "/citation-intent/text", payload)

    def citation_sentiment(
        self,
        document_title: str,
        full_text: str,
        *,
        reference_entries: str = "",
        **params: Any,
    ) -> dict[str, Any]:
        """识别论文引用句的引用情感。"""
        payload = {
            "document_title": document_title,
            "scientific_document_full_text": full_text,
            **params,
        }
        if reference_entries:
            payload["reference_entries"] = reference_entries
        return self._request("POST", "/citation-sentiment/text", payload)

    def relation_extract(self, record_id: str) -> dict[str, Any]:
        """根据上游 NER 响应的 record_id 抽取实体关系。"""
        if not record_id:
            raise ValueError("relation_extract 需要非空 NER record_id")
        return self._request(
            "POST",
            "/relation/from-ner-record",
            {"upstream_ner_record_id": record_id},
        )

    def deep_cluster(
        self,
        documents: list[dict[str, Any]],
        *,
        dimension: str = "technology",
        output_format: str = "JSON",
        **params: Any,
    ) -> dict[str, Any]:
        """对至少四篇文献执行深度聚类。"""
        if len(documents) < 4:
            raise ValueError("deep_cluster 至少需要四篇文献")
        metadata = [
            {
                "document_id": document["document_id"],
                "title": document.get("title", ""),
                "publication_date": document.get("publication_date", ""),
            }
            for document in documents
        ]
        return self._request(
            "POST",
            "/cluster/deep/texts",
            {
                "scientific_document_texts": documents,
                "document_metadata": metadata,
                "cluster_dimension": dimension,
                "output_format": output_format,
                **params,
            },
        )

    def cluster_labels(
        self,
        phrase_sets: list[dict[str, Any]],
        **params: Any,
    ) -> dict[str, Any]:
        """根据深度聚类结果生成统一主题标签。"""
        if not phrase_sets:
            raise ValueError("cluster_labels 需要非空 cluster_phrase_sets")
        return self._request(
            "POST",
            "/cluster-labels/generate",
            {"cluster_phrase_sets": phrase_sets, **params},
        )

    def structured_review(
        self,
        topic: str,
        documents: list[dict[str, Any]],
        **params: Any,
    ) -> dict[str, Any]:
        """根据至少两篇文献生成结构化综述。"""
        if len(documents) < 2:
            raise ValueError("structured_review 至少需要两篇文献")
        metadata = [
            {
                "document_id": document["document_id"],
                "title": document.get("title", ""),
                "publication_date": document.get("publication_date", ""),
            }
            for document in documents
        ]
        return self._request(
            "POST",
            "/review/structured/texts",
            {
                "topic_or_keywords": topic,
                "document_set": documents,
                "document_metadata": metadata,
                **params,
            },
        )

    @staticmethod
    def entities_of(response: dict[str, Any]) -> list[dict[str, Any]]:
        data = response.get("data") or {}
        return list(data.get("entity_results") or data.get("entities") or [])

    @staticmethod
    def data_of(response: dict[str, Any]) -> dict[str, Any]:
        data = response.get("data") or {}
        return dict(data) if isinstance(data, dict) else {"value": data}

    @staticmethod
    def definitions_of(response: dict[str, Any]) -> list[dict[str, Any]]:
        return list((response.get("data") or {}).get("definitions") or [])

    @staticmethod
    def questions_of(response: dict[str, Any]) -> list[Any]:
        data = response.get("data") or {}
        return list(
            data.get("structured_research_questions")
            or data.get("research_question_sentences")
            or []
        )

    @staticmethod
    def record_id_of(response: dict[str, Any]) -> str:
        return str(
            (response.get("meta") or {}).get("record_id")
            or (response.get("data") or {}).get("record_id")
            or ""
        )

    @staticmethod
    def triples_of(response: dict[str, Any]) -> list[dict[str, Any]]:
        data = response.get("data") or {}
        return list(
            data.get("relation_triples") or data.get("triples") or data.get("relations") or []
        )

    @staticmethod
    def keywords_of(response: dict[str, Any]) -> list[dict[str, Any]]:
        return list((response.get("data") or {}).get("keywords") or [])

    @staticmethod
    def classifications_of(response: dict[str, Any]) -> list[dict[str, Any]]:
        data = response.get("data") or {}
        return list(
            data.get("classifications") or data.get("multilevel_classification_results") or []
        )

    @staticmethod
    def clusters_of(response: dict[str, Any]) -> list[dict[str, Any]]:
        return list((response.get("data") or {}).get("clusters") or [])

    @staticmethod
    def cluster_labels_of(response: dict[str, Any]) -> list[dict[str, Any]]:
        return list((response.get("data") or {}).get("labels") or [])


def get_semantic_client(
    base_url: str | None = None,
    api_key: str | None = None,
    *,
    timeout: float | None = None,
) -> SemanticToolkitClient | None:
    """从显式参数或环境变量构造语义计算客户端；未配置服务地址时返回 None。"""
    raw_context = os.getenv("KG_SCRIPT_CTX", "")
    if raw_context:
        try:
            sandbox = json.loads(raw_context).get("_sandbox") is True
        except (ValueError, AttributeError):
            sandbox = False
        if sandbox:
            context = current_context()
            return context.semantic if context else None
    resolved_url = base_url or os.getenv("SEMANTIC_TOOLKIT_BASE_URL")
    if not resolved_url:
        return None
    resolved_key = api_key if api_key is not None else os.getenv("SEMANTIC_TOOLKIT_API_KEY")
    resolved_timeout = timeout
    if resolved_timeout is None:
        resolved_timeout = float(os.getenv("SEMANTIC_TOOLKIT_TIMEOUT", "600"))
    return SemanticToolkitClient(resolved_url, resolved_key, timeout=resolved_timeout)


@dataclass(frozen=True)
class ScriptConfig:
    """跨运行增量游标（``kg_script_watermark``，**只读**）。

    水位由平台在来源全部批次整链成功后按批次游标推进；脚本返回值里的
    ``_watermark``/``_checkpoint`` 元字段会被 activity 忽略（不归脚本管）。
    """

    watermark: str | None = None
    checkpoint: dict[str, Any] | None = None


class Context:
    """用户脚本运行上下文：懒构造平台客户端。

    Args:
        raw: activity 注入的 ctx dict。键：
            - mysql: {host, port, database, username, password}
            - graph: {base_url, space, api_key, timeout}
            - milvus: {uri, db_name, token, timeout}
            - llm: {api_key, base_url, model}
            - embedding: {api_key, base_url, model, dimensions}
            - semantic: {base_url, api_key, timeout}
            - watermark: str ISO | None
            - checkpoint: dict | None
            - stepId, attempt, prevOutputs, executionId, taskId, definitionId
    """

    def __init__(self, raw: dict[str, Any] | None) -> None:
        if raw and raw.get("_sandbox") is True:
            try:
                from .sandbox_proxy import public_context
            except ImportError:
                from sandbox_proxy import public_context
            raw = public_context(raw)
        self._raw: dict[str, Any] = raw or {}
        self._mysql: Any = _UNSET
        self._graph: Any = _UNSET
        self._milvus: Any = _UNSET
        self._llm: Any = _UNSET
        self._embedding: Any = _UNSET
        self._semantic: Any = _UNSET
        self._config = ScriptConfig(
            watermark=self._raw.get("watermark"),
            checkpoint=self._raw.get("checkpoint"),
        )
        self.step_id: str | None = self._raw.get("stepId")
        self.attempt: int | None = self._raw.get("attempt")
        self.prev_outputs: dict[str, Any] = self._raw.get("prevOutputs") or {}
        self.execution_id: str | None = self._raw.get("executionId")
        self.task_id: str | None = self._raw.get("taskId")
        self.definition_id: str | None = self._raw.get("definitionId")

    @property
    def config(self) -> ScriptConfig:
        return self._config

    @property
    def mysql(self) -> Any:
        """:class:`infra.mysql.MySQLClient` 或 None（未选数据源）。"""
        if self._raw.get("_sandbox") is True:
            return self._sandbox_resource("mysql")
        if self._mysql is _UNSET:
            params = self._raw.get("mysql")
            if not params:
                self._mysql = None
            else:
                from infra.mysql import MySQLClient

                client = MySQLClient(
                    host=params.get("host"),
                    port=int(params.get("port", 3306)),
                    database=params.get("database") or None,
                    username=params.get("username"),
                    password=params.get("password", ""),
                )
                self._mysql = _access.observe_mysql_client(client, params.get("database"))
        return self._mysql

    @property
    def graph(self) -> Any:
        """:class:`infra.graph_db.TRSGraphClient`（按所选图空间）或 None。"""
        if self._raw.get("_sandbox") is True:
            return self._sandbox_resource("graph")
        if self._graph is _UNSET:
            params = self._raw.get("graph")
            if not params:
                self._graph = None
            else:
                from infra.graph_db import TRSGraphClient
                from infra.graph_db.config import TRSGraphSettings

                settings = TRSGraphSettings(
                    base_url=params.get("base_url", "http://localhost:8090"),
                    space=params.get("space", "dev"),
                    api_key=params.get("api_key"),
                    timeout=int(params.get("timeout", 30)),
                )
                self._graph = TRSGraphClient(settings)
                self._graph.connect()
                self._graph = _access.ObservedGraphClient(self._graph)
        return self._graph

    @property
    def milvus(self) -> Any:
        """``pymilvus.MilvusClient``（按所选 Milvus 库）或 None。"""
        if self._raw.get("_sandbox") is True:
            return self._sandbox_resource("milvus")
        if self._milvus is _UNSET:
            params = self._raw.get("milvus")
            if not params:
                self._milvus = None
            else:
                from pymilvus import MilvusClient  # type: ignore[import-not-found]

                kwargs: dict[str, Any] = {
                    "uri": params.get("uri"),
                    "db_name": params.get("db_name", "default"),
                    "timeout": int(params.get("timeout", 30)),
                }
                if params.get("token"):
                    kwargs["token"] = params["token"]
                self._milvus = _access.ObservedMilvusClient(MilvusClient(**kwargs))
        return self._milvus

    @property
    def llm(self) -> Any:
        """:class:`infra.llm.LLMClient` 或 None（未选 LLM）。"""
        if self._raw.get("_sandbox") is True:
            return self._sandbox_resource("llm")
        if self._llm is _UNSET:
            params = self._raw.get("llm")
            if not params or not params.get("api_key"):
                self._llm = None
            else:
                from infra.llm import LLMClient

                self._llm = LLMClient(
                    api_key=params["api_key"],
                    base_url=params.get("base_url"),
                    model=params.get("model"),
                )
                self._llm = _access.ObservedLLMClient(self._llm)
        return self._llm

    @property
    def embedding(self) -> Any:
        """:class:`infra.llm.EmbeddingClient` 或 None（未选 embedding）。"""
        if self._raw.get("_sandbox") is True:
            return self._sandbox_resource("embedding")
        if self._embedding is _UNSET:
            params = self._raw.get("embedding")
            if not params or not params.get("api_key"):
                self._embedding = None
            else:
                from infra.llm import EmbeddingClient

                self._embedding = EmbeddingClient(
                    api_key=params["api_key"],
                    base_url=params.get("base_url"),
                    model=params.get("model"),
                    dimensions=params.get("dimensions"),
                )
                self._embedding = _access.ObservedEmbeddingClient(self._embedding)
        return self._embedding

    @property
    def semantic(self) -> SemanticToolkitClient | None:
        """语义计算工具客户端；支持 ctx.semantic 配置或环境变量。"""
        if self._raw.get("_sandbox") is True:
            return self._sandbox_resource("semantic")
        if self._semantic is _UNSET:
            params = self._raw.get("semantic") or {}
            self._semantic = get_semantic_client(
                params.get("base_url"),
                params.get("api_key"),
                timeout=float(params["timeout"]) if params.get("timeout") else None,
            )
        return self._semantic

    def _sandbox_resource(self, resource: str) -> Any:
        if not self._raw.get(resource):
            return None
        try:
            from .sandbox_proxy import make_proxy
        except ImportError:
            from sandbox_proxy import make_proxy
        attribute = "_" + resource
        if getattr(self, attribute) is _UNSET:
            setattr(self, attribute, make_proxy(resource, SemanticToolkitClient))
        return getattr(self, attribute)

    def to_dict(self) -> dict[str, Any]:
        """返回原始 ctx dict（调试用）。"""
        return dict(self._raw)


_current: Context | None = _UNSET


def current_context() -> Context | None:
    """单参脚本入口：读 ``KG_SCRIPT_CTX`` 环境变量构造 Context。

    未配置（legacy 运行 / 本地 dev）返回 None，脚本应自行降级。
    """
    global _current
    if _current is not _UNSET:
        return _current  # type: ignore[return-value]
    raw = os.environ.get("KG_SCRIPT_CTX")
    if not raw:
        _current = None
        return None
    try:
        _current = Context(json.loads(raw))
    except Exception:  # noqa: BLE001
        _current = None
    return _current  # type: ignore[return-value]


def reset_current_context() -> None:
    """测试用：清缓存。"""
    global _current
    _current = _UNSET


def step(fn=None, *, id=None):
    """``@step`` 装饰器：把顶层函数声明为抽取步（脚本唯一的入口声明方式）。

    平台在上传校验与执行计划组装时用 AST 静态识别该装饰器（不执行脚本）：

    - 步顺序 = 函数在源码中的出现顺序；
    - step id 默认取函数名，也可显式指定（可含 ``-``）::

        from kg_sdk import step

        @step                # id = "normalize"
        def normalize(payload): ...

        @step("resolve")     # id = "resolve"
        def do_resolve(payload): ...

    运行时本装饰器恒等返回原函数（sync/async 均可，runner 会 await）——步调度由
    Temporal workflow 按 plan 里的步清单逐 activity 驱动，装饰器不参与运行时调度。
    """
    if callable(fn) and id is None:
        return fn

    # @step("id") / @step(id="id") / @step()：fn 位是 id 字符串（或 None），返回恒等装饰器

    def decorate(f):
        return f

    return decorate


# 溯源采集（runner 子进程用：`from kg_sdk import access_report, flush_access_sidecar`）
access_report = _access.access_report
flush_access_sidecar = _access.flush_access_sidecar
