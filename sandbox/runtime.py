"""Boot code in the untrusted container; container isolation is the security boundary."""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import os
import sys
from pathlib import Path

MAX_BOOT = 32 * 1024 * 1024


def emit(value):
    sys.__stdout__.write(
        json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        + "\n"
    )
    sys.__stdout__.flush()


def main():
    # Read the boot line before importing user code; subsequent stdin lines are RPC replies.
    raw = sys.stdin.buffer.readline(MAX_BOOT + 1)
    if len(raw) > MAX_BOOT:
        raise ValueError("execution input limit exceeded")
    request = json.loads(raw)
    context = dict(request.get("context") or {})
    context["_sandbox"] = True
    os.environ["KG_SCRIPT_CTX"] = json.dumps(context, ensure_ascii=False)
    os.environ["KG_SCRIPT_SANDBOX"] = "1"
    sys.dont_write_bytecode = True
    sys.path.insert(0, "/opt/runtime/sdk")
    script = Path("/tmp/user_script.py")
    script.write_text(request["script"], encoding="utf-8")
    sys.stdout = sys.stderr
    spec = importlib.util.spec_from_file_location("user_script", script)
    module = importlib.util.module_from_spec(spec)
    sys.modules["user_script"] = module
    spec.loader.exec_module(module)
    function = getattr(module, request["function"])
    if not callable(function):
        raise TypeError("requested function is not callable")
    value = function(request["payload"])
    if inspect.isawaitable(value):
        value = asyncio.run(value)
    emit({"type": "result", "value": value})


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:  # noqa: BLE001 - report user exceptions including SystemExit
        emit({"type": "error", "message": f"{type(exc).__name__}: {str(exc)[:4000]}"})
        raise SystemExit(1) from None
