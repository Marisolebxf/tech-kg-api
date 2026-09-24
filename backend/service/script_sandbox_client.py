"""Authenticated NDJSON bridge to the isolated script runner.

Only public context crosses this boundary. Resource operations execute in the
worker broker, with independent authorization, never in the runner container.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import httpx

_MAX_REQUEST = 32 * 1024 * 1024
_MAX_LINE = 16 * 1024 * 1024
_MAX_REPLY = 8 * 1024 * 1024
_MAX_STREAM = 64 * 1024 * 1024
_MAX_RPCS = 1024
_RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class ScriptSandboxError(RuntimeError):
    """Safe failure message that may be shown to the job owner."""


def _configuration() -> tuple[str, str]:
    url = os.getenv("SCRIPT_RUNNER_URL", "").strip().rstrip("/")
    token = os.getenv("SCRIPT_RUNNER_TOKEN", "")
    try:
        parsed = httpx.URL(url)
    except (httpx.InvalidURL, ValueError) as exc:
        raise ScriptSandboxError("隔离脚本运行器地址无效") from exc
    if (
        not url
        or parsed.scheme not in {"http", "https"}
        or not parsed.host
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ScriptSandboxError("隔离脚本运行器未配置，请设置 SCRIPT_RUNNER_URL；禁止回退本地执行")
    if len(token) < 32 or any(char.isspace() for char in token):
        raise ScriptSandboxError("隔离脚本运行器令牌未配置或不足 32 字符")
    return url, token


async def _events(response: httpx.Response):
    pending = bytearray()
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > _MAX_STREAM:
            raise ScriptSandboxError("隔离脚本响应超过大小限制")
        pending.extend(chunk)
        while b"\n" in pending:
            line, _, rest = pending.partition(b"\n")
            pending = bytearray(rest)
            if len(line) > _MAX_LINE:
                raise ScriptSandboxError("隔离脚本消息超过大小限制")
            if line.strip():
                yield _decode_event(line)
        if len(pending) > _MAX_LINE:
            raise ScriptSandboxError("隔离脚本消息超过大小限制")
    if pending.strip():
        yield _decode_event(pending)


def _decode_event(line: bytes | bytearray) -> dict[str, Any]:
    try:
        event = json.loads(line)
    except (ValueError, UnicodeError) as exc:
        raise ScriptSandboxError("隔离脚本运行器返回无效消息") from exc
    if not isinstance(event, dict):
        raise ScriptSandboxError("隔离脚本运行器返回无效消息")
    return event


async def _invoke(broker, resource, method, args, kwargs):
    if inspect.iscoroutinefunction(broker.call):
        return await broker.call(resource, method, args, kwargs)
    result = await asyncio.to_thread(broker.call, resource, method, args, kwargs)
    return await result if inspect.isawaitable(result) else result


async def execute_script(
    script_path: Path | str,
    function_name: str,
    payload: bytes,
    public_context: dict[str, Any],
    timeout: float,
    broker,
) -> dict[str, Any]:
    """Run one script step, servicing bounded resource RPCs until completion."""
    run_id = None
    completed = False
    url = token = ""
    try:
        url, token = _configuration()
        if not 0 < timeout <= 86400:
            raise ScriptSandboxError("隔离脚本执行时限无效")
        script = await asyncio.to_thread(Path(script_path).read_bytes)
        if len(script) > 2 * 1024 * 1024:
            raise ScriptSandboxError("脚本超过大小限制")
        try:
            input_value = json.loads(payload)
            if not isinstance(input_value, dict):
                raise ValueError("object required")
            request_body = json.dumps(
                {
                    "script": script.decode("utf-8-sig"),
                    "function": function_name,
                    "payload": input_value,
                    "context": public_context,
                    "timeoutSeconds": timeout,
                },
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        except (ValueError, UnicodeError, TypeError) as exc:
            raise ScriptSandboxError("隔离脚本输入格式无效") from exc
        if len(request_body) > _MAX_REQUEST:
            raise ScriptSandboxError("隔离脚本输入超过大小限制")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(
                headers=headers,
                follow_redirects=False,
                trust_env=False,
                timeout=httpx.Timeout(timeout, connect=min(timeout, 10.0)),
                limits=httpx.Limits(max_connections=2, max_keepalive_connections=2),
            ) as client:
                async with client.stream(
                    "POST", f"{url}/execute", content=request_body
                ) as response:
                    response.raise_for_status()
                    run_id = None
                    rpc_ids = set()
                    async for event in _events(response):
                        kind = event.get("type")
                        if kind == "ready":
                            candidate = event.get("runId")
                            if (
                                run_id is not None
                                or not isinstance(candidate, str)
                                or not _RUN_ID.fullmatch(candidate)
                            ):
                                raise ScriptSandboxError("隔离脚本运行器会话无效")
                            run_id = candidate
                        elif kind == "rpc":
                            request_id = event.get("id")
                            resource, method = event.get("resource"), event.get("method")
                            args, kwargs = event.get("args", []), event.get("kwargs", {})
                            if (
                                not run_id
                                or event.get("runId") != run_id
                                or not isinstance(request_id, (str, int))
                                or isinstance(request_id, bool)
                                or len(str(request_id)) > 128
                                or request_id in rpc_ids
                                or not isinstance(resource, str)
                                or not 0 < len(resource) <= 64
                                or not isinstance(method, str)
                                or not 0 < len(method) <= 128
                                or not isinstance(args, list)
                                or not isinstance(kwargs, dict)
                            ):
                                raise ScriptSandboxError("隔离脚本资源请求无效")
                            rpc_ids.add(request_id)
                            if len(rpc_ids) > _MAX_RPCS:
                                raise ScriptSandboxError("隔离脚本资源调用次数超过限制")
                            try:
                                value = await _invoke(broker, resource, method, args, kwargs)
                                reply = {"id": request_id, "result": value}
                                reply_bytes = json.dumps(
                                    reply, ensure_ascii=True, allow_nan=False
                                ).encode("utf-8")
                                if len(reply_bytes) + 1 > _MAX_REPLY:
                                    raise ValueError("reply too large")
                            except Exception as exc:
                                # Only the broker's explicit safe errors may cross this boundary.
                                # Avoid importing its database dependencies in the protocol client.
                                module = sys.modules.get("service.script_resource_broker")
                                denied_type = getattr(module, "ScriptAccessDenied", None)
                                message = "资源操作被拒绝或失败"
                                if denied_type is not None and isinstance(exc, denied_type):
                                    message = str(exc)[:4096]
                                reply_bytes = json.dumps(
                                    {"id": request_id, "error": message}
                                ).encode()
                            async with client.stream(
                                "POST", f"{url}/runs/{run_id}/reply", content=reply_bytes
                            ) as reply_response:
                                reply_response.raise_for_status()
                        elif kind == "result" and run_id:
                            completed = True
                            report = getattr(broker, "access_report", lambda: None)()
                            wrapped = {"result": event.get("value")}
                            if report is not None:
                                wrapped["_access"] = report
                            return wrapped
                        elif kind == "error":
                            # Runner errors contain only bounded sandbox output or fixed
                            # infrastructure reasons; provider errors are sanitized above.
                            message = event.get("message")
                            if not isinstance(message, str) or not message.strip():
                                message = "请检查脚本和授权资源"
                            raise ScriptSandboxError(f"隔离脚本执行失败：{message[:4096]}")
                        else:
                            raise ScriptSandboxError("隔离脚本运行器返回未知消息")
                    raise ScriptSandboxError("隔离脚本运行器未返回执行结果")
    except TimeoutError as exc:
        raise ScriptSandboxError("隔离脚本执行超时") from exc
    except httpx.HTTPError as exc:
        raise ScriptSandboxError("隔离脚本运行器不可用或拒绝请求") from exc
    finally:
        if run_id and not completed:
            try:
                async with asyncio.timeout(2):
                    async with httpx.AsyncClient(
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=2,
                        follow_redirects=False,
                        trust_env=False,
                    ) as cancel_client:
                        async with cancel_client.stream("DELETE", f"{url}/runs/{run_id}"):
                            pass
            except Exception:
                pass
        try:
            async with asyncio.timeout(2):
                if inspect.iscoroutinefunction(broker.close):
                    await broker.close()
                else:
                    await asyncio.to_thread(broker.close)
        except Exception:
            pass
