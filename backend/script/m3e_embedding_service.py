"""OpenAI兼容的M3E-small在线文本向量服务。"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, field_validator
from starlette.concurrency import run_in_threadpool


class EmbeddingRequest(BaseModel):
    input: str | list[str]
    model: str | None = None
    dimensions: int | None = None

    @field_validator("input")
    @classmethod
    def validate_input(cls, value: str | list[str]) -> str | list[str]:
        texts = [value] if isinstance(value, str) else value
        if not texts or len(texts) > int(os.getenv("M3E_MAX_BATCH_SIZE", "64")):
            raise ValueError("input数量必须在1到M3E_MAX_BATCH_SIZE之间")
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("input中的文本不能为空")
        max_chars = int(os.getenv("M3E_MAX_INPUT_CHARS", "16000"))
        if any(len(text) > max_chars for text in texts):
            raise ValueError(f"单条文本不能超过{max_chars}个字符")
        return value


def create_app(model_factory: Callable[..., Any] | None = None) -> FastAPI:
    model_name = os.getenv("M3E_MODEL_NAME", "moka-ai/m3e-small")
    dimension = int(os.getenv("M3E_EMBEDDING_DIM", "512"))
    device = os.getenv("M3E_DEVICE", "cpu")
    batch_size = int(os.getenv("M3E_BATCH_SIZE", "8"))
    api_key = os.getenv("M3E_API_KEY", "")
    concurrency = max(1, int(os.getenv("M3E_MAX_CONCURRENCY", "1")))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        factory = model_factory
        if factory is None:
            from sentence_transformers import SentenceTransformer

            factory = SentenceTransformer
        model = await run_in_threadpool(factory, model_name, device=device)
        dimension_getter = getattr(model, "get_embedding_dimension", None)
        if dimension_getter is None:
            dimension_getter = model.get_sentence_embedding_dimension
        actual_dim = dimension_getter()
        if actual_dim != dimension:
            raise RuntimeError(
                f"模型{model_name}输出维度{actual_dim}与M3E_EMBEDDING_DIM={dimension}不一致"
            )
        app.state.model = model
        app.state.semaphore = asyncio.Semaphore(concurrency)
        yield
        app.state.model = None

    app = FastAPI(title="M3E Embedding Service", version="1.0.0", lifespan=lifespan)

    def authorize(authorization: str | None) -> None:
        if api_key and authorization != f"Bearer {api_key}":
            raise HTTPException(status_code=401, detail="无效的Embedding服务凭据")

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok" if getattr(app.state, "model", None) is not None else "loading",
            "model": model_name,
            "dimension": dimension,
            "device": device,
        }

    @app.post("/v1/embeddings")
    async def embeddings(
        request: EmbeddingRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, object]:
        authorize(authorization)
        requested_model = request.model or model_name
        if requested_model != model_name:
            raise HTTPException(status_code=400, detail=f"仅支持模型{model_name}")
        if request.dimensions is not None and request.dimensions != dimension:
            raise HTTPException(status_code=400, detail=f"仅支持{dimension}维向量")
        texts = [request.input] if isinstance(request.input, str) else request.input
        started = time.time()
        async with app.state.semaphore:
            vectors = await run_in_threadpool(
                app.state.model.encode,
                texts,
                batch_size=batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        data = [
            {"object": "embedding", "index": index, "embedding": vector.tolist()}
            for index, vector in enumerate(vectors)
        ]
        return {
            "object": "list",
            "data": data,
            "model": model_name,
            "usage": {"prompt_tokens": 0, "total_tokens": 0},
            "elapsed_ms": round((time.time() - started) * 1000, 2),
        }

    return app


app = create_app()
