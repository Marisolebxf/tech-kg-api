"""科技产业链点 TOP-N 事件关系业务（九大业务之一）请求/响应模型。

对齐前端 service-modules.ts 的 industry-chain-event 契约：
端点 POST /api/v1/kg-service/industry-node-top-events，请求 {chain_node_id, top_n, event_type,
time_range}，响应 data={events, experts, enterprises, risk_level, top_events, relations}。
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator

from biz.schemas.tech_enterprise_relation_business import EntityProvenance

# 标识类字段允许的字符：字母数字下划线、中文、间隔号、点、连字符。
_ID_LIKE_PATTERN = re.compile(r"[\w一-鿿·.\-]+")

# 月级 time_range 端点格式：YYYY-MM（如 2025-01）。用于 industry-chain-event 算法测试页
# 两个 month 选择器合并出的 "YYYY-MM~YYYY-MM" 月份区间（保留月份，后端按 occur_date[:7] 筛）。
_YYYY_MM_PATTERN = re.compile(r"\d{4}-\d{2}")


def _is_yyyymm(s: str) -> bool:
    """是否为合法 YYYY-MM（含月份 1-12 校验）。"""
    if not s or not _YYYY_MM_PATTERN.fullmatch(s) or len(s) != 7:
        return False
    return 1 <= int(s[5:7]) <= 12


class IndustryNodeTopEventsRequest(BaseModel):
    chain_node_id: str = Field(
        ..., max_length=64, description="产业链节点标识，如 IC0007007（集成电路设计）"
    )
    top_n: int = Field(10, ge=1, le=50, description="返回事件数量")
    event_type: str = Field(
        "", max_length=64, description="事件类型筛选（financing/bankruptcy/bid/...）"
    )
    time_range: str = Field("", description="事件时间范围筛选，如 2025-2026")
    max_orgs: int = Field(
        20, ge=1, le=50, description="链节点下最多扫描企业数（按 chain_score 排序）"
    )

    @field_validator("chain_node_id", "event_type", mode="before")
    @classmethod
    def normalize_id_like(cls, value: str | None) -> str | None:
        """标识类字段：拒绝超长、空格与 !@#￥%& 等异常字符。

        与同事关系 (expert_colleague_relation) 的专家标识校验保持一致，覆盖测试用例：
        超长字符 / 异常字符。event_type 可留空（默认 ""），留空时跳过校验。
        """
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        if value == "":
            return value
        if re.search(r"\s", value):
            raise ValueError("输入不能包含空格或 !@#￥%& 等异常字符")
        value = value.strip()
        if len(value) > 64:
            raise ValueError("输入长度不能超过 64 个字符")
        if not _ID_LIKE_PATTERN.fullmatch(value):
            raise ValueError("输入不能包含空格或 !@#￥%& 等异常字符")
        return value

    @field_validator("top_n", mode="before")
    @classmethod
    def _validate_top_n(cls, value: object) -> int:
        """top_n：必须是 1-50 的整数，留空取默认 10。

        覆盖 0826 任务用例：top_n 输入非数字 → 提示「必须是数字」；
        top_n 不在范围 → 提示「取值范围为 1-50」。前端 top_n 为文本框（可输入任意字符），
        故此处兼容字符串/浮点/布尔等脏输入，统一给出中文提示，再交由 Field 的 ge/le 兜底。
        """
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return 10
        if isinstance(value, bool):  # bool 是 int 子类，但语义上不是数字输入
            raise ValueError("top_n 必须是数字")
        if isinstance(value, int):
            n: int = value
        elif isinstance(value, float) and value.is_integer():
            n = int(value)
        elif isinstance(value, str) and re.fullmatch(r"\d+", value.strip()):
            n = int(value.strip())
        else:
            raise ValueError("top_n 必须是数字")
        if n < 1 or n > 50:
            raise ValueError("top_n 取值范围为 1-50")
        return n

    @field_validator("max_orgs", mode="before")
    @classmethod
    def _validate_max_orgs(cls, value: object) -> int:
        """max_orgs：必须是 1-50 的整数，留空取默认 20。

        与 _validate_top_n 同口径：非数字 → 提示「必须是数字」；
        不在范围 → 提示「取值范围为 1-50」。前端 max_orgs 为文本框（可输入任意字符），
        故此处兼容字符串/浮点/布尔等脏输入，统一给出中文提示，再交由 Field 的 ge/le 兜底。
        """
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return 20
        if isinstance(value, bool):  # bool 是 int 子类，但语义上不是数字输入
            raise ValueError("max_orgs 必须是数字")
        if isinstance(value, int):
            n: int = value
        elif isinstance(value, float) and value.is_integer():
            n = int(value)
        elif isinstance(value, str) and re.fullmatch(r"\d+", value.strip()):
            n = int(value.strip())
        else:
            raise ValueError("max_orgs 必须是数字")
        if n < 1 or n > 50:
            raise ValueError("max_orgs 取值范围为 1-50")
        return n

    @model_validator(mode="after")
    def validate_time_range(self) -> IndustryNodeTopEventsRequest:
        """time_range 支持两种粒度：

        - 月级 "YYYY-MM~YYYY-MM"（industry-chain-event 算法测试页两个 month 选择器合并，
          保留月份；可单端开放如 "2025-01~" / "~2025-06"）；按月比较，不晚于当前月。
        - 年级 "YYYY-YYYY"（兼容旧格式与 graph-query 页；可单端开放如 "2025-"）；
          按年比较，不晚于当前年。

        校验：起始不晚于结束；起止均不晚于当前时间（测试用例：填未来应提示超出当前时间）。
        用 ~ 分隔月级区间，避免与 YYYY-MM 自带的 - 冲突。
        """
        if not self.time_range:
            return self
        if "~" in self.time_range:
            lo, _, hi = self.time_range.partition("~")
            current_month = date.today().strftime("%Y-%m")
            if lo and not _is_yyyymm(lo):
                raise ValueError("time_range_start 格式应为 YYYY-MM，如 2025-01") from None
            if hi and not _is_yyyymm(hi):
                raise ValueError("time_range_end 格式应为 YYYY-MM，如 2025-06") from None
            if lo and hi and lo > hi:
                raise ValueError("time_range_start 不能晚于 time_range_end")
            if lo and lo > current_month:
                raise ValueError("time_range_start 不能晚于当前时间")
            if hi and hi > current_month:
                raise ValueError("time_range_end 不能晚于当前时间")
            return self
        lo, _, hi = self.time_range.partition("-")
        current_year = date.today().strftime("%Y")
        try:
            lo_year = int(lo[:4]) if lo else None
            hi_year = int(hi[:4]) if hi else None
        except ValueError:
            raise ValueError("time_range 格式应为 YYYY-YYYY，如 2025-2026") from None
        if lo_year and hi_year and lo_year > hi_year:
            raise ValueError("time_range_start 不能晚于 time_range_end")
        if lo_year and lo_year > int(current_year):
            raise ValueError("time_range_start 不能晚于当前时间")
        if hi_year and hi_year > int(current_year):
            raise ValueError("time_range_end 不能晚于当前时间")
        return self


class TopEventItem(BaseModel):
    event_id: str
    event_type: str | None = None
    occur_date: str | None = None
    amount: str | None = None
    title: str | None = None
    impact_score: float = 0.0
    rank: int = 0
    org_id: str | None = None
    org_name: str | None = None
    confidence: float = 0.0  # 事件置信度（按事件类型规则赋值）


class EventExpertRelation(BaseModel):
    event_id: str
    event_title: str | None = None
    expert_id: str
    expert_name: str | None = None
    role: str | None = None
    org_id: str
    org_name: str | None = None


class IndustryNodeTopEventsResponse(BaseModel):
    chain_node_id: str
    chain_node_name: str | None = None
    chain_name: str | None = None
    node_imp_level: str | None = None
    events: int = 0  # TOP-N 事件数
    experts: int = 0  # 关联专家数
    enterprises: int = 0  # 关联企业数
    risk_level: str = ""  # 高/中/低
    top_events: list[TopEventItem] = Field(default_factory=list)
    relations: list[EventExpertRelation] = Field(default_factory=list)
    # 标书分析维度：节点影响 / 发展趋势 / 机遇挖掘（从 TOP 事件池规则派生）
    node_impact: str = ""
    trend: str = ""
    opportunity: str = ""
    confidence: float = 0.0  # 综合置信度（按风险等级赋值）
    evidence: list[str] = Field(default_factory=list)
    # 实体溯源：vid -> 源数据表/英文字段名/源记录值/入图批次/入图时间，供前端溯源栏展示
    # 字段名不用 provenance，避免被前端 liveProvenance(data.provenance) 误匹配（与同事/企业关系同口径）
    entity_provenance: dict[str, EntityProvenance] = Field(default_factory=dict)
