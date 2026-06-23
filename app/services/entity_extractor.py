"""
实体抽取模块
基于智谱 GLM 大模型，从非结构化文本中抽取知识图谱实体
支持：工作经历、教育背景、论文摘要、专利摘要、项目摘要
"""
from __future__ import annotations

import json
import re
import os
from dotenv import load_dotenv

try:
    from zai import ZhipuAiClient
except ImportError:  # pragma: no cover - SDK may be absent or incompatible
    ZhipuAiClient = None

load_dotenv() 
# API Key 从环境变量读取，不硬编码
API_KEY = os.getenv("ZHIPUAI_API_KEY", "")
MODEL   = os.getenv("MODEL","glm-5.1")

client = ZhipuAiClient(api_key=API_KEY) if ZhipuAiClient and API_KEY else None

_POSITION_TERMS = [
    "教授",
    "副教授",
    "研究员",
    "副研究员",
    "助理研究员",
    "高级工程师",
    "工程师",
    "讲师",
    "博士后",
    "博士生导师",
    "硕士生导师",
    "主任",
    "副主任",
    "总监",
    "CEO",
    "CFO",
    "CTO",
    "COO",
]

_DEGREE_TERMS = ["博士", "硕士", "学士", "本科"]
_TECH_FIELDS = [
    "知识图谱",
    "自然语言处理",
    "机器学习",
    "深度学习",
    "计算机视觉",
    "大模型",
    "数据挖掘",
    "图数据库",
    "推荐系统",
    "语义检索",
    "智能决策",
    "智能计算",
    "多模态",
]


def _new_entity(entity_id: int, text: str, entity_type: str) -> dict[str, str]:
    return {"id": f"E{entity_id}", "text": text, "type": entity_type}


def _append_entity(entities: list[dict[str, str]], seen: set[str], text: str, entity_type: str) -> None:
    normalized = re.sub(r"\s+", "", text or "").strip()
    if not normalized:
        return
    if entity_type != "TimePeriod" and len(normalized) < 2:
        return
    if normalized in seen:
        return
    seen.add(normalized)
    entities.append(_new_entity(len(entities) + 1, normalized, entity_type))


def _fallback_extract(text: str, source_type: str = "general") -> list[dict[str, str]]:
    """Rule-based fallback extractor when LLM is unavailable."""
    normalized_text = text.strip()
    if not normalized_text:
        return []

    entities: list[dict[str, str]] = []
    seen: set[str] = set()

    def add_matches(pattern: str, entity_type: str) -> None:
        for match in re.finditer(pattern, normalized_text):
            _append_entity(entities, seen, match.group(0), entity_type)

    # 通用时间段
    add_matches(r"\d{4}年(?:\d{1,2}月)?(?:[—\-~至到]\s*(?:今|\d{4}年(?:\d{1,2}月)?))?", "TimePeriod")
    add_matches(r"\d{4}\.\d{1,2}(?:\s*[—\-~至到]\s*(?:今|\d{4}\.\d{1,2}))?", "TimePeriod")

    # 机构/公司
    add_matches(r"[\u4e00-\u9fffA-Za-z·（）()]{2,40}?(?:大学|学院|研究院|研究所|实验室|中心|公司|集团|系|所)", "Institution")
    add_matches(r"[\u4e00-\u9fffA-Za-z·（）()]{2,40}?(?:有限公司|股份公司|科技有限公司|科技公司|集团公司|研究院)", "Company")

    # 职称/职位
    for term in _POSITION_TERMS:
        if term in normalized_text:
            _append_entity(entities, seen, term, "Position")

    # 学位
    for term in _DEGREE_TERMS:
        if term in normalized_text:
            _append_entity(entities, seen, term, "Degree")

    # 技术领域/研究方向
    for term in _TECH_FIELDS:
        if term in normalized_text:
            _append_entity(entities, seen, term, "TechField")

    # 基金/项目
    add_matches(r"[\u4e00-\u9fffA-Za-z·（）()]{0,20}(?:基金|项目|课题|专项|计划)", "Fund")
    for term in ["国家自然科学基金", "重点研发计划", "青年基金", "面上项目"]:
        if term in normalized_text:
            _append_entity(entities, seen, term, "Fund")

    # 通用补充
    if source_type == "general":
        for term in ["高校", "科研院所", "企业", "平台"]:
            if term in normalized_text:
                _append_entity(entities, seen, term, "Other")

    # 让结果更稳定：按出现顺序去重后返回
    return entities

# 实体类型定义
ENTITY_TYPES = {
    "Scholar":     "学者/人名",
    "Institution": "机构/学校/大学",
    "Company":     "企业/公司",
    "Position":    "职位/职称",
    "Degree":      "学位",
    "Major":       "专业/学科",
    "TechField":   "技术领域/研究方向",
    "Fund":        "基金项目/资助来源",
    "TimePeriod":  "时间段/年份",
    "Other":       "其他重要实体（不属于以上类型）",
}

# 不同文本类型对应的重点实体
FOCUS_TYPES = {
    "work":       ["Scholar", "Institution", "Company", "Position", "TimePeriod", "Other"],
    "education":  ["Scholar", "Institution", "Degree", "Major", "TimePeriod", "Other"],
    "abstract":   ["TechField", "Institution", "Fund", "Other"],
    "general":    list(ENTITY_TYPES.keys()),
}


def build_prompt(text: str, source_type: str = "general") -> str:
    """构建 Prompt，根据文本类型聚焦不同实体"""
    focus = FOCUS_TYPES.get(source_type, FOCUS_TYPES["general"])
    types = ", ".join(
        f"{k}({ENTITY_TYPES[k]})" for k in focus
    )
    return f"""你是实体识别专家。从文本中识别实体，严格按照以下要求输出。

【实体类型】只能使用以下类型，不能使用其他类型：
{types}

【输出格式】只输出JSON，不输出任何解释或其他内容：
{{"entities": [{{"id": "E1", "text": "实体原文", "type": "实体类型"}}]}}

【示例】
文本: 2020年至今，清华大学计算机系，副教授
输出: {{"entities": [{{"id": "E1", "text": "清华大学", "type": "Institution"}}, {{"id": "E2", "text": "副教授", "type": "Position"}}, {{"id": "E3", "text": "2020年至今", "type": "TimePeriod"}}]}}

【待识别文本】
{text.strip()}"""


def extract(text: str, source_type: str = "general") -> list:
    """
    调用大模型抽取实体
    :param text: 输入文本
    :param source_type: 文本类型 work/education/abstract/general
    :return: 实体列表
    """
    if not text or not text.strip():
        return []
    if client is None:
        return _fallback_extract(text, source_type)

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "你是实体识别专家，只输出JSON，不输出任何解释。"},
                {"role": "user",   "content": build_prompt(text, source_type)}
            ]
        )
        raw = resp.choices[0].message.content.strip()
        # 去除可能的 markdown 代码块包裹
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        entities = json.loads(raw).get("entities", [])
        if entities:
            return entities
        return _fallback_extract(text, source_type)

    except json.JSONDecodeError as e:
        print(f"[extraction] JSON 解析失败: {e}\nraw={raw}")
        return _fallback_extract(text, source_type)
    except Exception as e:
        print(f"[extraction] 调用异常: {e}")
        return _fallback_extract(text, source_type)
