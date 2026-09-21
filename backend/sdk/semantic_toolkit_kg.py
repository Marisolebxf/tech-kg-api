"""语义计算工具库 · 知识图谱平台接入 SDK（v1.0，2026-09-21）

零依赖（仅 requests），19 个功能点全覆盖，实体/关系抽取优先。
所有方法返回统一信封 dict（与 REST 响应完全一致），失败抛 SemanticToolkitError。

快速上手：
    from semantic_toolkit_kg import SemanticToolkit

    kg = SemanticToolkit("http://127.0.0.1:8000")
    # 实体抽取（构建图谱节点）
    ent = kg.ner_research(text="Zhang等提出的深度学习方法应用于桥梁监测。")
    entities = kg.entities_of(ent)          # [{"text":..., "type":..., "std_zh":...}, ...]
    # 关系抽取（构建图谱边）—— 需先有 NER 记录
    rel = kg.relation_extract(record_id=kg.record_id(ent))
    triples = kg.triples_of(rel)            # [{"subject":...,"relation":...,"object":...}, ...]
    # 分类/关键词等其余工具同风格调用
"""
from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

import requests

__all__ = ["SemanticToolkit", "SemanticToolkitError"]
__version__ = "1.0.0"


class SemanticToolkitError(RuntimeError):
    """业务失败（code != 0 / HTTP 错误）。.status_code 与 .response 保留原始信息。"""

    def __init__(self, message: str, *, status_code: int = 0, response: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response = response


def _form_value(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class SemanticToolkit:
    """语义计算工具库客户端。

    Args:
        base_url: 服务地址，如 "http://127.0.0.1:8000"（自动拼 /api/v1）。
        api_key: 服务端开启鉴权时的 X-API-Key。
        timeout: 单请求超时秒数（批量任务建议 ≥600）。
    """

    def __init__(self, base_url: str, api_key: Optional[str] = None, *, timeout: float = 600.0) -> None:
        self._base = base_url.rstrip("/") + "/api/v1"
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers["Accept"] = "application/json"
        if api_key:
            self._session.headers["X-API-Key"] = api_key

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "SemanticToolkit":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # 基础通道
    # ------------------------------------------------------------------ #

    def _post_json(self, endpoint: str, payload: Mapping[str, Any]) -> dict:
        r = self._session.post(self._base + endpoint, json=dict(payload), timeout=self._timeout)
        return self._check(r)

    def _post_files(self, endpoint: str, file_field: str, paths: Iterable[str | Path],
                    payload: Optional[Mapping[str, Any]] = None) -> dict:
        files, streams = [], []
        try:
            for p in paths:
                path = Path(p)
                stream = path.open("rb")
                streams.append(stream)
                files.append((file_field, (path.name, stream,
                                           mimetypes.guess_type(path.name)[0] or "application/octet-stream")))
            data = {k: _form_value(v) for k, v in dict(payload or {}).items() if v is not None}
            r = self._session.post(self._base + endpoint, files=files, data=data, timeout=self._timeout)
            return self._check(r)
        finally:
            for s in streams:
                s.close()

    @staticmethod
    def _check(r: requests.Response) -> dict:
        try:
            body = r.json()
        except ValueError as exc:
            raise SemanticToolkitError(f"服务返回非 JSON（HTTP {r.status_code}）",
                                       status_code=r.status_code, response=r.text) from exc
        if r.status_code // 100 != 2 or int(body.get("code", 0) or 0) != 0:
            detail = (body.get("detail")
                      or (body.get("data") or {}).get("error_summary")
                      or body.get("message")
                      or f"HTTP {r.status_code}")
            raise SemanticToolkitError(str(detail), status_code=r.status_code, response=body)
        return body

    def upload_resource(self, resource_key: str, file_path: str | Path) -> dict:
        """上传用户资源（术语库/映射表/训练集等），返回 {resource_id, ...} 描述符。

        resource_key 取值见 API 文档「资源上传」节（如 domain_terminology_library、
        classification_standard_mapping_table、preprocessed_training_set 等）。
        """
        path = Path(file_path)
        with path.open("rb") as f:
            r = self._session.post(self._base + "/semantic-resources/upload",
                                   data={"resource_key": resource_key},
                                   files={"upload": (path.name, f, "application/json")},
                                   timeout=self._timeout)
        return self._check(r)

    def health(self) -> dict:
        return self._session.get(self._base.rsplit("/api/v1", 1)[0] + "/health",
                                 timeout=30).json()

    # ------------------------------------------------------------------ #
    # 实体抽取（图谱节点来源）
    # ------------------------------------------------------------------ #

    def ner_general(self, text: str, **params: Any) -> dict:
        """通用领域命名实体识别（人物/地点/组织/事件）。"""
        return self._post_json("/ner/general/text", {"text": text, **params})

    def ner_general_file(self, path: str | Path, **params: Any) -> dict:
        return self._post_files("/ner/general/file", "file", [path], params)

    def ner_research(self, text: str, **params: Any) -> dict:
        """科研领域命名实体识别（方法/数据集/仪器/理论/主题五类）。"""
        return self._post_json("/ner/research/text", {"text": text, **params})

    def ner_research_file(self, path: str | Path, **params: Any) -> dict:
        return self._post_files("/ner/research/file", "file", [path], params)

    def ner_domain(self, text: str, *, domain: str = "", **params: Any) -> dict:
        """专业领域命名实体识别（本体限定类型体系）。"""
        payload = {"text": text, **params}
        if domain:
            payload["domain"] = domain
        return self._post_json("/ner/domain/text", payload)

    def ner_domain_file(self, path: str | Path, **params: Any) -> dict:
        return self._post_files("/ner/domain/file", "file", [path], params)

    # ------------------------------------------------------------------ #
    # 关系抽取（图谱边来源）
    # ------------------------------------------------------------------ #

    def relation_extract(self, record_id: str) -> dict:
        """实体关系抽取：传入上游 NER 记录的 record_id（先跑 ner_* 取本 SDK
        record_id()），返回三元组/依存/知识网络。"""
        return self._post_json("/relation/from-ner-record",
                               {"upstream_ner_record_id": record_id})

    # ------------------------------------------------------------------ #
    # 自动分类
    # ------------------------------------------------------------------ #

    def classify_zh(self, text: str, title: str = "", **params: Any) -> dict:
        payload = {"text": text, **params}
        if title:
            payload["document_title"] = title
        return self._post_json("/classify/clc/zh/text", payload)

    def classify_zh_file(self, path: str | Path, **params: Any) -> dict:
        return self._post_files("/classify/clc/zh/file", "file", [path], params)

    def classify_en(self, text: str, title: str = "", **params: Any) -> dict:
        payload = {"text": text, **params}
        if title:
            payload["document_title"] = title
        return self._post_json("/classify/clc/en/text", payload)

    def classify_en_file(self, path: str | Path, **params: Any) -> dict:
        return self._post_files("/classify/clc/en/file", "file", [path], params)

    def classify_domain(self, text: str, *, domain: str = "", title: str = "", **params: Any) -> dict:
        payload = {"text": text, **params}
        if title:
            payload["document_title"] = title
        if domain:
            payload["domain"] = domain
        return self._post_json("/classify/domain/text", payload)

    # ------------------------------------------------------------------ #
    # 关键词 / 研究问题 / 概念定义 / 引用 / 语步
    # ------------------------------------------------------------------ #

    def keywords_zh(self, text: str, **params: Any) -> dict:
        return self._post_json("/keywords/zh/text", {"text": text, **params})

    def keywords_zh_file(self, path: str | Path, **params: Any) -> dict:
        return self._post_files("/keywords/zh/file", "file", [path], params)

    def keywords_en(self, text: str, **params: Any) -> dict:
        return self._post_json("/keywords/en/text", {"text": text, **params})

    def keywords_en_file(self, path: str | Path, **params: Any) -> dict:
        return self._post_files("/keywords/en/file", "file", [path], params)

    def research_questions(self, text: str, *, title: str = "",
                           text_format: str = "自动识别", **params: Any) -> dict:
        payload = {"text": text, "text_format_requirement": text_format, **params}
        if title:
            payload["document_title"] = title
        return self._post_json("/research-question/text", payload)

    def research_questions_file(self, path: str | Path, **params: Any) -> dict:
        return self._post_files("/research-question/file", "file", [path], params)

    def definitions(self, text: str, **params: Any) -> dict:
        return self._post_json("/concept-definition/text", {"text": text, **params})

    def definitions_file(self, path: str | Path, **params: Any) -> dict:
        return self._post_files("/concept-definition/file", "file", [path], params)

    def citation_intent(self, full_text: str, *, title: str = "",
                        reference_entries: str = "", **params: Any) -> dict:
        """引用意图识别：文献全文（含 [n] 标记）；reference_entries 为参考文献条目原文（选填）。"""
        payload = {"scientific_document_full_text": full_text, **params}
        if title:
            payload["document_title"] = title
        if reference_entries:
            payload["reference_entries"] = reference_entries
        return self._post_json("/citation-intent/text", payload)

    def citation_sentiment(self, full_text: str, *, title: str = "",
                           reference_entries: str = "", **params: Any) -> dict:
        payload = {"scientific_document_full_text": full_text, **params}
        if title:
            payload["document_title"] = title
        if reference_entries:
            payload["reference_entries"] = reference_entries
        return self._post_json("/citation-sentiment/text", payload)

    def moves_zh(self, abstract: str, **params: Any) -> dict:
        """中文摘要语步识别。"""
        return self._post_json("/move/abstract/zh/text", {"text": abstract, **params})

    def moves_en(self, abstract: str, **params: Any) -> dict:
        return self._post_json("/move/abstract/en/text", {"text": abstract, **params})

    def fund_moves(self, project_name: str, full_text: str, **params: Any) -> dict:
        """基金项目语步识别（须为申请书/进展/结题类文档，论文会明确报错）。"""
        return self._post_json("/move/fund/zh/text",
                               {"project_name": project_name, "text": full_text, **params})

    # ------------------------------------------------------------------ #
    # 聚类 / 综述
    # ------------------------------------------------------------------ #

    def deep_cluster(self, documents: list[dict], metadata: Optional[list[dict]] = None,
                     *, dimension: str = "technology", output_format: str = "JSON",
                     **params: Any) -> dict:
        """深度聚类：documents=[{document_id,title,text,publication_date},...]（≥4 篇）。

        metadata 与 documents 逐篇对应（document_id+title+publication_date），
        缺省时自动从 documents 生成。
        """
        meta = metadata or [{"document_id": d["document_id"], "title": d.get("title", ""),
                             "publication_date": d.get("publication_date", "")} for d in documents]
        return self._post_json("/cluster/deep/texts",
                               {"scientific_document_texts": documents,
                                "document_metadata": meta,
                                "cluster_dimension": dimension,
                                "output_format": output_format, **params})

    def deep_cluster_files(self, paths: list[str | Path], **params: Any) -> dict:
        return self._post_files("/cluster/deep/files", "files", paths, params)

    def cluster_labels(self, phrase_sets: list[dict], **params: Any) -> dict:
        """聚类标签生成：phrase_sets=[{cluster_id, phrases:[...]}, ...]。"""
        return self._post_json("/cluster-labels/generate",
                               {"cluster_phrase_sets": phrase_sets, **params})

    def structured_review(self, topic: str, documents: list[dict], **params: Any) -> dict:
        """结构化综述：documents=[{document_id,title,text,publication_date},...]（≥2 篇）。"""
        meta = [{"document_id": d["document_id"], "title": d.get("title", ""),
                 "publication_date": d.get("publication_date", "")} for d in documents]
        return self._post_json("/review/structured/texts",
                               {"topic_or_keywords": topic, "document_set": documents,
                                "document_metadata": meta, **params})

    # ------------------------------------------------------------------ #
    # 结果取用辅助（知识图谱构建友好）
    # ------------------------------------------------------------------ #

    @staticmethod
    def entities_of(response: dict) -> list[dict]:
        """从 NER 响应取实体列表（含 std_zh/std_en 标准词，直接作图谱节点属性）。"""
        data = response.get("data") or {}
        return data.get("entities") or data.get("entity_results") or []

    @staticmethod
    def triples_of(response: dict) -> list[dict]:
        """从关系抽取响应取三元组列表（subject/relation/object + 触发词/依存路径）。"""
        data = response.get("data") or {}
        return data.get("triples") or data.get("relations") or []

    @staticmethod
    def record_id(response: dict) -> str:
        """取响应的 record_id（关系抽取的上游凭证）。"""
        return str((response.get("meta") or {}).get("record_id") or "")

    @staticmethod
    def task_id(response: dict) -> str:
        return str((response.get("meta") or {}).get("task_id") or "")
