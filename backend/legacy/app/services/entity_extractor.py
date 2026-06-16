"""
实体抽取模块
基于智谱 GLM 大模型，从非结构化文本中抽取知识图谱实体
支持：工作经历、教育背景、论文摘要、专利摘要、项目摘要
"""

import json
import os
import re

from dotenv import load_dotenv

try:
    from zai import ZhipuAiClient
except ImportError:  # pragma: no cover - SDK may be absent or incompatible
    ZhipuAiClient = None

load_dotenv()
# API Key 从环境变量读取，不硬编码
API_KEY = os.getenv("ZHIPUAI_API_KEY", "")
MODEL = os.getenv("MODEL", "glm-5.1")

client = ZhipuAiClient(api_key=API_KEY) if ZhipuAiClient and API_KEY else None

# 实体类型定义
ENTITY_TYPES = {
    "Scholar": "学者/人名",
    "Institution": "机构/学校/大学",
    "Company": "企业/公司",
    "Position": "职位/职称",
    "Degree": "学位",
    "Major": "专业/学科",
    "TechField": "技术领域/研究方向",
    "Fund": "基金项目/资助来源",
    "TimePeriod": "时间段/年份",
    "Other": "其他重要实体（不属于以上类型）",
}

# 不同文本类型对应的重点实体
FOCUS_TYPES = {
    "work": ["Scholar", "Institution", "Company", "Position", "TimePeriod", "Other"],
    "education": ["Scholar", "Institution", "Degree", "Major", "TimePeriod", "Other"],
    "abstract": ["TechField", "Institution", "Fund", "Other"],
    "general": list(ENTITY_TYPES.keys()),
}


def build_prompt(text: str, source_type: str = "general") -> str:
    """构建 Prompt，根据文本类型聚焦不同实体"""
    focus = FOCUS_TYPES.get(source_type, FOCUS_TYPES["general"])
    types = ", ".join(f"{k}({ENTITY_TYPES[k]})" for k in focus)
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
        return []

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "你是实体识别专家，只输出JSON，不输出任何解释。"},
                {"role": "user", "content": build_prompt(text, source_type)},
            ],
        )
        raw = resp.choices[0].message.content.strip()
        # 去除可能的 markdown 代码块包裹
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        return json.loads(raw).get("entities", [])

    except json.JSONDecodeError as e:
        print(f"[extraction] JSON 解析失败: {e}\nraw={raw}")
        return []
    except Exception as e:
        print(f"[extraction] 调用异常: {e}")
        return []
