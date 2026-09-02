"""文本入参统一校验规则。

所有人工输入的文本框统一约束:长度不超过 64 个字符,且不允许空格或
!@#￥%& 等异常字符(关键词类字段允许空格)。与业务模块既有校验口径
(expert_colleague_relation / tech_enterprise_relation_business 等)保持一致。
"""

from __future__ import annotations

import re

MAX_TEXT_LENGTH = 64

# 标识类字段(专家 ID、节点 VID、边 ID 等):不允许空格
IDENTIFIER_TEXT_PATTERN = re.compile(r"[\w一-鿿·.\-]+")
# 边 ID:scholar_id->enterprise_id@0,额外允许 > 与 @
EDGE_ID_TEXT_PATTERN = re.compile(r"[\w一-鿿·.\->@]+")
# 关键词类字段(名称、说明、原因等):允许空格、括号、顿号、逗号、斜杠和常用标点
KEYWORD_TEXT_PATTERN = re.compile(r"[\w一-鿿·.\-()（）、，,/:：;；\s]+")
# URL 类字段(Base URL 等):允许 : / . ? # = & % ~ -
URL_TEXT_PATTERN = re.compile(r"[\w:/.?#=&%~\-]+")
# 密钥类字段(API Key 等):字母数字与常见分隔符,不允许空格
SECRET_TEXT_PATTERN = re.compile(r"[\w.\-+=/]+")

ABNORMAL_CHARS_HINT = "!@#￥%& 等异常字符"

# GET 查询参数(Query(pattern=...))用的正则字符串,允许空值
KEYWORD_QUERY_PATTERN = r"^[\w一-鿿·.\-()（）、，,/:：;；\s]*$"
IDENTIFIER_QUERY_PATTERN = r"^[\w一-鿿·.\->@]*$"


def check_text(
    value: str | None,
    *,
    label: str,
    pattern: re.Pattern[str] = IDENTIFIER_TEXT_PATTERN,
    allow_space: bool = False,
) -> str | None:
    """校验文本入参:超长与异常字符;空值原样放行(必填由 Field 约束)。

    allow_space=True 时使用关键词字符集(含空格);否则使用传入的
    标识类字符集。返回原值,不做 strip,由调用方决定清洗方式。
    """
    if value is None or value == "":
        return value
    if len(value) > MAX_TEXT_LENGTH:
        raise ValueError(f"{label}长度不能超过 {MAX_TEXT_LENGTH} 个字符")
    effective = KEYWORD_TEXT_PATTERN if allow_space else pattern
    if not effective.fullmatch(value):
        prefix = "" if allow_space else "空格或 "
        raise ValueError(f"{label}不能包含{prefix}{ABNORMAL_CHARS_HINT}")
    return value
