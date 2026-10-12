"""Per-business default language model; public default remains on LlmConfig."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from db_model.base import Base


class BusinessLlmDefault(Base):
    __tablename__ = "platform_business_llm_default"
    business_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    config_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
