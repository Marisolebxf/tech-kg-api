"""关系抽取 API 的请求/响应模型。"""

from pydantic import BaseModel, ConfigDict, Field


class RelationExtractionRequest(BaseModel):
    """从文本中抽取实体与关系三元组。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "text": "马云创立了阿里巴巴集团，阿里巴巴集团位于浙江省杭州市。",
                "method": "rule",
            }
        }
    )

    text: str = Field(..., min_length=1, description="待抽取关系的文本")
    method: str = Field(
        default="rule",
        pattern="^(rule|llm|hybrid)$",
        description="抽取方法: rule（规则匹配）/ llm（大模型） / hybrid（混合）",
    )


class BatchRelationExtractionRequest(BaseModel):
    """批量从多个文本中抽取实体与关系三元组。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "texts": [
                    "马云创立了阿里巴巴集团",
                    "任正非创立了华为技术有限公司",
                ],
                "method": "rule",
            }
        }
    )

    texts: list[str] = Field(..., min_length=1, description="待抽取的文本列表")
    method: str = Field(
        default="rule",
        pattern="^(rule|llm|hybrid)$",
        description="抽取方法: rule / llm / hybrid",
    )
