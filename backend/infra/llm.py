"""LLM 客户端（智谱 GLM，OpenAI 兼容）。带超时与降级。"""

from __future__ import annotations

import logging
from typing import Any

from openai import OpenAI

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "glm-4.7-flash"
DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
DEFAULT_MAX_TOKENS = 2048
DEFAULT_TIMEOUT = 40


class LLMClient:
    """智谱 GLM 客户端。glm-4.7-flash 为推理模型，需较大 max_tokens，读 message.content。"""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self._model = model
        self._base_url = base_url
        self._api_key = api_key
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=DEFAULT_TIMEOUT)

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def api_key(self) -> str:
        return self._api_key

    def synthesize(self, prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS) -> str | None:
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                # 统一关闭沉思（thinking），避免推理模型返回思考文本导致 JSON 解析失败
                extra_body={"thinking": {"type": "disabled"}},
            )
            return resp.choices[0].message.content or None
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM synthesize failed, degrading: %s", exc)
            return None


class EmbeddingClient:
    """OpenAI 兼容 embedding 客户端。embed/embed_one 失败降级返回 None。"""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = "embedding-3",
        dimensions: int | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url
        self._api_key = api_key
        self._dimensions = dimensions
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=DEFAULT_TIMEOUT)

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        """批量 embedding。返回与输入等长的向量列表；失败返回 None。"""
        if not texts:
            return []
        try:
            kwargs: dict[str, Any] = {"model": self._model, "input": texts}
            if self._dimensions:
                kwargs["dimensions"] = self._dimensions
            resp = self._client.embeddings.create(**kwargs)
            return [d.embedding for d in resp.data]
        except Exception as exc:  # noqa: BLE001
            logger.warning("embedding embed failed, degrading: %s", exc)
            return None

    def embed_one(self, text: str) -> list[float] | None:
        result = self.embed([text])
        if result is None:
            return None
        return result[0] if result else []


_client: LLMClient | None = None


def _resolve_settings() -> tuple[str, str, str] | None:
    """通过 service.llm_config 解析当前 LLM 配置（DB 优先，env 回退）。失败返回 None。"""
    try:
        from service.llm_config import resolve_llm_settings

        return resolve_llm_settings()
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取 LLM 配置失败，LLM 功能降级: %s", exc)
        return None


def get_llm_client() -> LLMClient | None:
    """进程级单例。无 key 时返回 None（调用方走降级）。"""
    global _client
    if _client is not None:
        return _client
    settings = _resolve_settings()
    if settings is None:
        logger.info("未配置 LLM（DB 与 env 均无默认配置），LLM 功能降级")
        return None
    api_key, base_url, model = settings
    _client = LLMClient(api_key=api_key, base_url=base_url, model=model)
    return _client


def reset_llm_client() -> None:
    """重置单例。配置变更后由 service 层调用，下次 get_llm_client 重建。"""
    global _client
    _client = None
