"""
实体抽取模块
基于智谱 GLM 大模型，从非结构化文本中抽取知识图谱实体
支持：工作经历、教育背景、论文摘要、专利摘要、项目摘要
"""

import json

from dotenv import load_dotenv

try:
    from zai import ZhipuAiClient
except ImportError:  # pragma: no cover - SDK may be absent or incompatible
    ZhipuAiClient = None

load_dotenv()

_client = None
_model = None


def get_client():
    """Create the LLM client lazily so import/startup never depends on network config.

    配置来源由 service.llm_config.resolve_llm_settings 决定（DB 优先，env 回退）。
    """
    global _client, _model
    if _client is not None:
        return _client, _model
    from service.llm_config import resolve_llm_settings

    settings = resolve_llm_settings()
    if settings is None:
        return None, None
    api_key, _base_url, model = settings
    if not ZhipuAiClient or not api_key:
        return None, None
    try:
        _client = ZhipuAiClient(api_key=api_key)
        _model = model
    except Exception as e:
        print(f"[extraction] 客户端初始化失败: {e}")
        return None, None
    return _client, _model


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
    client, model = get_client()
    if client is None:
        return []

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是实体识别专家，只输出JSON，不输出任何解释。"},
                {"role": "user", "content": build_prompt(text, source_type)},
            ],
        )
        raw = resp.choices[0].message.content.strip()
        # 去除可能的 markdown 代码块包裹，避免用可产生灾难性回溯的正则。
        if raw.startswith("```"):
            opening_end = raw.find("\n")
            opening = raw[:opening_end].strip().lower() if opening_end >= 0 else ""
            if opening in {"```", "```json"}:
                raw = raw[opening_end + 1 :]
            if raw.rstrip().endswith("```"):
                raw = raw.rstrip()[:-3].rstrip()
        return json.loads(raw).get("entities", [])

    except json.JSONDecodeError as e:
        print(f"[extraction] JSON 解析失败: {e}\nraw={raw}")
        return []
    except Exception as e:
        print(f"[extraction] 调用异常: {e}")
        return []
