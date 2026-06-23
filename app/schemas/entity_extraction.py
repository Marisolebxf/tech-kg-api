"""实体抽取 请求/响应数据模型"""

from typing import Optional
from pydantic import BaseModel


class ExtractRequest(BaseModel):
    text: str
    source_type: Optional[str] = "general"
    """
    source_type 可选值：
    - work        工作经历（抽取：机构、职位、时间段）
    - education   教育背景（抽取：学校、学位、专业、时间段）
    - abstract    摘要文本（抽取：技术领域、机构、基金）
    - general     通用（抽取所有实体类型）
    """

    model_config = {
        "json_schema_extra": {
            "example": {
                "text": "2010年—至今，北京大学计算机科学与技术系，教授",
                "source_type": "work"
            }
        }
    }


class EntityItem(BaseModel):
    id: str
    text: str
    type: str


class ExtractResponse(BaseModel):
    source_type: str
    entity_count: int
    entities: list[EntityItem]
    task_id: Optional[str] = None
    task_status: str = "completed"
    persist_to_graph: bool = False


class ExtractionTaskStatusResponse(BaseModel):
    task_id: str
    task_kind: str = ""
    status: str
    source_type: str
    entity_count: int = 0
    written_entities: int = 0
    job_node_id: str = ""
    source_hash: str = ""
    storage_backend: str = ""
    execution_backend: str = ""
    error: str = ""
    queued_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    updated_at: str = ""
