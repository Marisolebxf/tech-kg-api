"""Schema 脚本 LLM 安全校验。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from infra.llm import LLMClient

LLM_RESPONSE_FORMAT_ERROR = 'LLM 返回格式异常'


@dataclass
class ScriptSecurityVerdict:
    safe: bool
    issues: list[str] = field(default_factory=list)
    summary: str = ""


_SECURITY_PROMPT_TEMPLATE = """你是一名 Python 安全审计专家。请审计下面这个将被注册到知识图谱构建平台、用于实体/关系数据抽取的 Python 脚本的安全性。

脚本文件名: {filename}

脚本源码:
```python
{source}
```

重点检查以下风险（不限于）：
1. 危险 import：os、subprocess、socket、shutil、ctypes、pickle、marshal、multiprocessing 等可执行系统/网络/进程操作的模块。
2. 危险调用：eval、exec、compile、__import__、os.system、os.popen、subprocess.* 等。
3. 网络访问：socket、urllib、requests、httpx 等向外发起请求（尤其是动态构造 URL 或下载远程代码）。
4. 文件越界读写：读写工作目录之外的路径、读写密钥文件（如 ~/.ssh、/etc/passwd、.env）。
5. 读取敏感信息：os.environ、密钥、凭据、token。
6. 进程派生：subprocess.Popen、os.fork、os.exec*。
7. 远程代码下载并执行：urllib + exec、requests.get + exec、base64 解码后 exec。
8. 代码混淆：base64/hex/marshal 解码后 exec/eval，动态构造字符串再执行。

判定标准：脚本应只做"接收一行数据 → 返回结构化结果"的纯计算变换。任何可能影响宿主环境安全的行为都判为不安全。

请严格只返回如下 JSON（不要任何额外文字、不要 markdown 代码栅栏）：
{{"safe": true或false, "issues": ["问题1", "问题2"], "summary": "一句话总结"}}

若脚本安全，issues 为空数组，summary 给出简短肯定评价。
若不安全，issues 列出每个具体问题（中文短句），summary 概括整体风险。"""


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _build_prompt(filename: str, source: str) -> str:
    return _SECURITY_PROMPT_TEMPLATE.format(filename=filename, source=source)


def _parse_verdict(raw: str) -> ScriptSecurityVerdict:
    match = _JSON_OBJECT_RE.search(raw)
    if not match:
        return ScriptSecurityVerdict(
            safe=False,
            issues=["LLM 返回格式异常：未找到 JSON"],
            summary=LLM_RESPONSE_FORMAT_ERROR,
        )
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return ScriptSecurityVerdict(
            safe=False,
            issues=["LLM 返回格式异常：JSON 解析失败"],
            summary=LLM_RESPONSE_FORMAT_ERROR,
        )
    if not isinstance(data, dict):
        return ScriptSecurityVerdict(
            safe=False,
            issues=["LLM 返回格式异常：根节点不是对象"],
            summary=LLM_RESPONSE_FORMAT_ERROR,
        )
    safe = data.get("safe")
    issues = data.get("issues", [])
    summary = data.get("summary", "")
    if not isinstance(safe, bool):
        return ScriptSecurityVerdict(
            safe=False,
            issues=["LLM 返回格式异常：safe 字段缺失或非布尔"],
            summary=LLM_RESPONSE_FORMAT_ERROR,
        )
    if not isinstance(issues, list) or not all(isinstance(i, str) for i in issues):
        issues = []
    if not isinstance(summary, str):
        summary = ""
    return ScriptSecurityVerdict(safe=safe, issues=issues, summary=summary)


def review_script_security(client: LLMClient, filename: str, source: str) -> ScriptSecurityVerdict:
    prompt = _build_prompt(filename, source)
    raw = client.synthesize(prompt, max_tokens=1024)
    if raw is None:
        return ScriptSecurityVerdict(
            safe=False,
            issues=["LLM 调用失败，未返回结果"],
            summary="LLM 调用失败",
        )
    return _parse_verdict(raw)
