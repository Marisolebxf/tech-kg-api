"""专利编号的无损展示值与跨数据源比较键。"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

IDENTIFIER_CLEAN_RE = re.compile(r"[^0-9a-z]+")
CN_APPLICATION_RE = re.compile(r"^(?:cn|zl)?(\d{12})(?:[a-z]|\d)?$")


def identifier_key(value: Any) -> str:
    """通用编号比较键：只消除大小写、空格和连接符差异。"""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return IDENTIFIER_CLEAN_RE.sub("", text)


def application_number_key(value: Any) -> str:
    """生成中国申请号比较键，不改写或伪造源字段。"""
    key = identifier_key(value)
    matched = CN_APPLICATION_RE.fullmatch(key)
    return f"cn{matched.group(1)}" if matched else key
