"""图算法作业接口请求模型（camelCase 别名与 schema_management 同款）。"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 边类型（EDGE）名：与 NebulaGraph EDGE 命名规则一致
EDGE_TYPE_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]{0,127}$"
# 算法名：小写字母开头，与 TRSAlgorithmClient 注册表一致
ALGORITHM_NAME_PATTERN = r"^[a-z][a-z0-9]*$"


def _to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class CamelModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True, alias_generator=_to_camel, str_strip_whitespace=True
    )


class AlgorithmSubmitRequest(CamelModel):
    """提交算法作业；params 为各算法专有参数（camelCase 键，如 maxIter）。"""

    space: str = Field(min_length=1, max_length=64)
    algorithm: str = Field(min_length=1, max_length=64, pattern=ALGORITHM_NAME_PATTERN)
    labels: list[str] = Field(min_length=1, max_length=20)
    params: dict[str, Any] = Field(default_factory=dict)
    has_weight: bool = False
    weight_cols: list[str] | None = None
    # 图库 vid 为字符串（如 "Person:1"），算法计算需编码，默认开启
    encode_id: bool = True
    partition_num: int = Field(default=1, ge=1, le=10000)

    @field_validator("labels", "weight_cols")
    @classmethod
    def validate_label_names(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        for item in value:
            if not re.fullmatch(EDGE_TYPE_NAME_PATTERN, item or ""):
                raise ValueError(f"边类型名称不合法：{item!r}")
        return value
