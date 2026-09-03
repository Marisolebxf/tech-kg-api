"""图谱构建服务测试替身（真实 HTTP 服务）。

人工处理模块的「重跑下发」在真实链路里由图谱构建服务承接。由于图谱构建尚未开发，
本脚本起一个**真实监听端口的 uvicorn 服务**实现 handoff 契约（POST /internal/review-resumes），
让后端 ``dispatch_resume`` 走真实 HTTP 调用（``REVIEW_RERUN_MODE=real``），而非 mock。

它是真实服务而非 mock：真实 socket、真实 Bearer 鉴权、真实 Idempotency-Key 校验、
真实拉取 correction 并校验 payloadSha256、真实 §6/§7 幂等与重试语义。

回调（execution-events）由测试按真实 HTTP 自行驱动，以精确控制时序与中间态校验。

启动：
    uv run python script/run_graph_build_double.py --port 18098 \
        --backend-url http://127.0.0.1:18099 --token test-service-token
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel


def _dump(v: Any) -> str:
    """与后端 service.manual_review_production.dump 完全一致的规范 JSON。"""
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def _sha(v: Any) -> str:
    return hashlib.sha256(_dump(v).encode()).hexdigest()


class ResumeRequest(BaseModel):
    reviewId: str
    correctionId: str
    correctionVersion: int
    stepId: str
    scope: str
    sourceTaskId: str
    batchId: str | None = None
    workflow: dict[str, Any]
    correctionUrl: str


class ResumeResponse(BaseModel):
    accepted: bool
    executionId: str
    workflowId: str
    runId: str
    status: str


def create_app(backend_url: str, token: str) -> FastAPI:
    app = FastAPI(title="graph-build-double")
    state: dict[str, dict[str, Any]] = {}
    seq: list[int] = [0]

    def mint() -> str:
        seq[0] += 1
        return f"GB-{seq[0]:06d}"

    def verify_token(authorization: str | None) -> None:
        if not authorization or authorization != f"Bearer {token}":
            raise HTTPException(401, "图谱构建服务认证失败")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/internal/review-resumes", responses={422: {"description": "请求无法处理"}, 502: {"description": "上游服务返回错误"}})
    async def review_resumes(
        body: ResumeRequest,
        request: Request,
        authorization: str | None = Header(None),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> ResumeResponse:
        verify_token(authorization)
        if idempotency_key != body.correctionId:
            raise HTTPException(422, "Idempotency-Key 必须等于 correctionId")

        sid = body.sourceTaskId or ""
        rec = state.get(body.correctionId)

        # §6 幂等：相同 correctionId 且上一次未失败 → 返回同一 executionId，不重复下发。
        # §7 重试：上一次失败（retried=True）→ 颁发新 executionId。
        if rec is None:
            exec_id = mint()
            rec = {"execId": exec_id, "retried": False}
            state[body.correctionId] = rec
        elif rec["retried"]:
            exec_id = mint()
            rec["execId"] = exec_id
            rec["retried"] = False
        else:
            exec_id = rec["execId"]
            return ResumeResponse(
                accepted=True,
                executionId=exec_id,
                workflowId=body.workflow.get("workflowId", ""),
                runId="double",
                status="QUEUED",
            )

        # 真实拉取 correction 并校验 payloadSha256 完整性（handoff 契约）。
        # correctionUrl 为相对路径（/api/v1/...），需基于后端地址补全。
        curl = body.correctionUrl
        if curl.startswith("/"):
            curl = backend_url.rstrip("/") + curl
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                curl,
                headers={"Authorization": f"Bearer {token}"},
            )
            if r.status_code != 200:
                raise HTTPException(502, f"拉取 correction 失败: {r.status_code}")
            correction = r.json()["data"]
        expected = correction.get("payloadSha256")
        actual = _sha(correction.get("payload"))
        if expected != actual:
            raise HTTPException(422, "correction payloadSha256 校验失败")

        # 失败标记：sourceTaskId 含 FAIL → 本次重跑将失败（由测试驱动 RERUN_FAILED 回调），
        # 标记 retried=True，使下一次下发（retry）按 §7 颁发新 executionId。
        if "FAIL" in sid:
            rec["retried"] = True

        return ResumeResponse(
            accepted=True,
            executionId=exec_id,
            workflowId=body.workflow.get("workflowId", ""),
            runId="double",
            status="QUEUED",
        )

    @app.get("/internal/double/state")
    async def double_state(authorization: str | None = Header(None)) -> dict[str, Any]:
        verify_token(authorization)
        return {"corrections": state, "seq": seq[0]}

    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument(
        "--backend-url",
        default=os.getenv("GRAPH_BUILD_BACKEND_URL", "http://127.0.0.1:18099"),
    )
    parser.add_argument(
        "--token", default=os.getenv("GRAPH_BUILD_SERVICE_TOKEN", "test-service-token")
    )
    args = parser.parse_args()

    import uvicorn

    app = create_app(args.backend_url, args.token)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
