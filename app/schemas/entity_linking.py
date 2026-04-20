"""实体对齐与消歧 API 的请求/响应模型。"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EntityAlignmentRequest(BaseModel):
    """不传 kg_a/kg_b、或传空列表 [] 时，使用内置示例图谱。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "top_k": 3,
            }
        }
    )

    kg_a: list[dict[str, Any]] | None = Field(
        default=None,
        description="中文侧实体列表。省略、null 或 [] 时使用内置 KG_A。",
    )
    kg_b: list[dict[str, Any]] | None = Field(
        default=None,
        description="英文侧实体列表。省略、null 或 [] 时使用内置 KG_B。",
    )
    top_k: int = Field(default=3, ge=1, le=50, description="向量召回候选数。")


class EntityDisambiguationRequest(BaseModel):
    """不传 kb、或传空列表 [] 时，使用内置示例知识库。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "text": "苹果今天在发布会上推出了新款iPhone 16。",
                "mention": "苹果",
                "top_k": 5,
            }
        }
    )

    text: str = Field(..., min_length=1, description="含实体提及的完整句子")
    mention: str = Field(..., min_length=1, description="待链接的实体表面形式")
    kb: list[dict[str, Any]] | None = Field(
        default=None,
        description="可选。省略、null 或 [] 时使用内置歧义知识库 KB。",
    )
    top_k: int = Field(default=5, ge=1, le=50, description="向量召回候选数。")
