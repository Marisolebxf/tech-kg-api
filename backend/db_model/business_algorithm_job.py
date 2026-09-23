"""远程图算法任务的可信空间归属，不依赖调用方传入的空间。"""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db_model.base import Base


class BusinessAlgorithmJob(Base):
    __tablename__ = "kg_business_algorithm_job"

    job_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    graph_space: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
