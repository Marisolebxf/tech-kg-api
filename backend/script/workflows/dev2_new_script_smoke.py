"""Dev2 冒烟测试用 kg.custom.python 工作流脚本。

调用新的 entity_extractors_one_entity.project_entity 抽取器（dry-run），把统计结果回包。
不调任何旧 ETL 入口（load_project_graph 等），只走新的「一实体一脚本」实现。

runner（service/temporal_workflows.py:execute_python_script）会把本函数返回值 print 成 JSON
到 stdout 然后用 json.loads 解析；所以本函数自身不能 print 到 stdout，日志走 stderr。
"""

from __future__ import annotations

import json
import subprocess
import sys


def workflow(payload: dict) -> dict:
    limit = int(payload.get("limit", 1))
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "script.entity_extractors_one_entity.project_entity",
            "--dry-run",
            "--limit",
            str(limit),
            "--log-level",
            "INFO",
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        return {
            "status": "error",
            "returncode": proc.returncode,
            "stderr_tail": proc.stderr[-3000:],
            "stdout_tail": proc.stdout[-1000:],
        }
    try:
        parsed = json.loads(proc.stdout)
        return {
            "status": "ok",
            "limit": limit,
            "result": parsed,
            "stderr_tail": proc.stderr[-500:],
        }
    except json.JSONDecodeError:
        return {
            "status": "ok_non_json_stdout",
            "limit": limit,
            "raw_stdout_tail": proc.stdout[-2000:],
            "stderr_tail": proc.stderr[-1000:],
        }
