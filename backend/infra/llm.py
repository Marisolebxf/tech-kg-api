"""LLM 客户端（智谱 GLM，OpenAI 兼容）。带超时与降级。"""

from __future__ import annotations

import logging
import os

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
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=DEFAULT_TIMEOUT)

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


_client: LLMClient | None = None


def get_llm_client() -> LLMClient | None:
    """进程级单例。无 key 时返回 None（调用方走降级）。"""
    global _client
    if _client is not None:
        return _client
    api_key = os.getenv("LLM_API_KEY") or os.getenv("ZHIPUAI_API_KEY")
    if not api_key:
        logger.info("LLM_API_KEY 未配置，LLM 功能降级")
        return None
    model = os.getenv("LLM_MODEL", DEFAULT_MODEL)
    base_url = os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL)
    _client = LLMClient(api_key=api_key, base_url=base_url, model=model)
    return _client


def reset_llm_client() -> None:
    """测试用：重置单例。"""
    global _client
    _client = None
