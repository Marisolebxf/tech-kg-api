"""关系抽取：从文本中抽取实体与关系三元组（Demo 级实现）。"""

import re
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================================
# 数据结构
# ============================================================

@dataclass
class Entity:
    """实体"""
    text: str
    label: str  # PERSON, ORG, LOC, DATE, PRODUCT, EVENT, ...
    start: int = -1
    end: int = -1

    def to_dict(self):
        return asdict(self)


@dataclass
class Relation:
    """关系三元组"""
    head: Entity
    relation: str
    tail: Entity
    confidence: float = 1.0
    source: str = "unknown"  # rule / llm / hybrid

    def to_dict(self):
        return {
            "head": self.head.to_dict(),
            "relation": self.relation,
            "tail": self.tail.to_dict(),
            "confidence": self.confidence,
            "source": self.source,
        }

    def to_triple(self):
        return (self.head.text, self.relation, self.tail.text)


# ============================================================
# 触发词映射（用于快速筛选可能包含关系的句子）
# ============================================================

TRIGGER_WORDS = {
    "就职于": ["担任", "出任", "就任", "任职", "就职", "现任", "CEO", "总裁", "董事长", "总经理"],
    "创立": ["创立", "创办", "创建", "建立", "成立", "发起", "创始人"],
    "位于": ["位于", "坐落于", "总部", "地处"],
    "籍贯": ["出生", "生于", "来自", "籍贯"],
    "收购": ["收购", "并购", "兼并", "买下", "购入"],
    "合作": ["合作", "联合", "共同", "签署", "战略合作"],
    "产品": ["推出", "发布", "研发", "开发", "研制"],
    "投资": ["投资", "注资", "领投", "融资"],
    "配偶": ["结婚", "夫妻", "配偶", "妻子", "丈夫"],
}

# 内置示例文本
EXAMPLE_TEXTS = [
    {
        "title": "科技企业",
        "text": (
            "马云创立了阿里巴巴集团，阿里巴巴集团位于浙江省杭州市。"
            "马云出生于浙江省杭州市。"
            "张勇担任阿里巴巴集团的CEO。"
            "阿里巴巴集团投资了蚂蚁集团。"
            "阿里巴巴集团与腾讯在云计算领域战略合作。"
            "阿里巴巴集团推出了通义千问大模型产品。"
        ),
    },
    {
        "title": "人物关系",
        "text": (
            "任正非创立了华为技术有限公司，华为技术有限公司位于广东省深圳市。"
            "孟晚舟担任华为技术有限公司的CFO。"
            "华为技术有限公司推出了鸿蒙操作系统产品。"
            "华为技术有限公司与赛力斯集团联合发布了问界汽车。"
            "李彦宏创立了百度公司，百度公司位于北京市。"
        ),
    },
    {
        "title": "商业并购",
        "text": (
            "马斯克创立了特斯拉公司，特斯拉公司位于美国得克萨斯州。"
            "马斯克担任特斯拉公司的CEO。"
            "微软公司投资了OpenAI公司。"
            "微软公司与OpenAI公司战略合作。"
            "谷歌公司收购了DeepMind公司。"
            "谷歌公司推出了Gemini大模型产品。"
        ),
    },
]


# ============================================================
# 1. 基于规则的关系抽取
# ============================================================

class RuleBasedExtractor:
    """基于规则的关系抽取器"""

    # 常见动词/助词集合，用于过滤NER误匹配
    _VERB_CHARS = set('了着过在到被把给让向对于从用将以与和为')

    def _recognize_entities(self, text: str) -> list[Entity]:
        """简易命名实体识别（基于规则 + 词典）"""
        entities: list[Entity] = []
        seen_texts: dict[str, tuple] = {}

        def _add(ent_text: str, label: str, start: int, end: int):
            while ent_text and ent_text[0] in self._VERB_CHARS:
                ent_text = ent_text[1:]
                start += 1
            while ent_text and ent_text[-1] in self._VERB_CHARS:
                ent_text = ent_text[:-1]
                end -= 1
            if len(ent_text) < 2:
                return
            if ent_text in seen_texts:
                return

            to_remove = []
            for i, existing in enumerate(entities):
                if existing.text in ent_text and existing.text != ent_text:
                    to_remove.append(i)
                elif ent_text in existing.text and ent_text != existing.text:
                    return

            for i in sorted(to_remove, reverse=True):
                old = entities.pop(i)
                if old.text in seen_texts:
                    del seen_texts[old.text]

            seen_texts[ent_text] = (label, start, end)
            entities.append(Entity(text=ent_text, label=label, start=start, end=end))

        # 上下文感知提取
        context_patterns = [
            # 创立
            (r'([\u4e00-\u9fff]{2,3}?)[，,]?\s*(?:创立|创办|创建)\s*(?:了\s*)?([\u4e00-\u9fffA-Za-z]{1,15}(?:有限公司|股份公司|集团|公司|银行|基金|资本))', 'PERSON', 'ORG'),
            # 担任
            (r'([\u4e00-\u9fff]{2,3}?)[，,]?\s*(?:担任|出任|就任|现任)\s*(?:了?\s*)?([\u4e00-\u9fffA-Za-z]{1,15}(?:有限公司|股份公司|集团|公司|银行|基金|资本))', 'PERSON', 'ORG'),
            # 出生于
            (r'([\u4e00-\u9fff]{2,3}?)[，,]?\s*(?:出生于|生于|来自|籍贯)\s*([\u4e00-\u9fff]{1,8}(?:省|市|区|县|州|国))', 'PERSON', 'LOC'),
            # 位于
            (r'([\u4e00-\u9fffA-Za-z]{1,15}(?:有限公司|股份公司|集团|公司|银行|基金|资本))[，,]?\s*(?:位于|坐落于|总部在|设于|地处)\s*([\u4e00-\u9fff]{1,8}(?:省|市|区|县|州|国))', 'ORG', 'LOC'),
            # 投资
            (r'([\u4e00-\u9fffA-Za-z]{1,15}(?:有限公司|股份公司|集团|公司|银行|基金|资本))[，,]?\s*(?:投资|注资|领投)\s*(?:了\s*)?([\u4e00-\u9fffA-Za-z]{1,15}(?:有限公司|股份公司|集团|公司|银行|基金|资本))', 'ORG', 'ORG'),
            # 收购
            (r'([\u4e00-\u9fffA-Za-z]{1,15}(?:有限公司|股份公司|集团|公司|银行|基金|资本))[，,]?\s*(?:收购|并购|兼并|买下|购入)\s*(?:了\s*)?([\u4e00-\u9fffA-Za-z]{1,15}(?:有限公司|股份公司|集团|公司|银行|基金|资本))', 'ORG', 'ORG'),
            # 合作
            (r'([\u4e00-\u9fffA-Za-z]{1,15}(?:有限公司|股份公司|集团|公司|银行|基金|资本))[，,]?\s*(?:与|和)\s*([\u4e00-\u9fffA-Za-z]{1,15}(?:有限公司|股份公司|集团|公司|银行|基金|资本))', 'ORG', 'ORG'),
            # 产品
            (r'([\u4e00-\u9fffA-Za-z]{1,15}(?:有限公司|股份公司|集团|公司|银行|基金|资本))[，,]?\s*(?:推出|发布|研发|开发|研制)\s*(?:了\s*)?([\u4e00-\u9fffA-Za-z0-9]{2,10}(?:大模型|操作系统|系统|平台|手机|汽车|芯片))', 'ORG', 'PRODUCT'),
        ]

        for pattern, h_type, t_type in context_patterns:
            for m in re.finditer(pattern, text):
                _add(m.group(1), h_type, m.start(1), m.end(1))
                _add(m.group(2), t_type, m.start(2), m.end(2))

        # 通用模式补充
        general_patterns = [
            (r'[\u4e00-\u9fffA-Za-z]{1,6}(?:有限公司|股份公司|集团|公司|银行|基金|资本|研究院)', 'ORG'),
            (r'[\u4e00-\u9fff]{1,4}(?:省|自治区)[\u4e00-\u9fff]{1,4}(?:市|区|县)', 'LOC'),
            (r'[\u4e00-\u9fff]{1,4}(?:省|市|区|县|镇)', 'LOC'),
            (r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', 'PERSON'),
        ]
        for pattern, label in general_patterns:
            for m in re.finditer(pattern, text):
                _add(m.group(), label, m.start(), m.end())

        return entities

    def extract(self, text: str, entities: list[Entity] | None = None) -> list[Relation]:
        """从文本中抽取关系（文本级正则直接提取）"""
        if entities is None:
            entities = self._recognize_entities(text)

        # 文本级正则直接提取
        text_level_patterns = [
            # 创立
            (r'([\u4e00-\u9fff]{2,4}?)[，,]?\s*(?:创立|创办|创建)\s*(?:了\s*)?([\u4e00-\u9fffA-Za-z]{1,15}(?:有限公司|股份公司|集团|公司|银行|基金|资本))', '创立', 'PERSON', 'ORG'),
            # 就职
            (r'([\u4e00-\u9fff]{2,4}?)[，,]?\s*(?:担任|出任|就任|现任)\s*(?:了?\s*)?([\u4e00-\u9fffA-Za-z]{1,15}(?:有限公司|股份公司|集团|公司|银行|基金|资本))\s*(?:的\s*)?(?:CEO|CFO|CTO|COO|董事长|总裁|总经理|总监|创始人|联合创始人|首席\w+官|VP|副总裁)', '就职于', 'PERSON', 'ORG'),
            # 位于
            (r'([\u4e00-\u9fffA-Za-z]{1,15}(?:有限公司|股份公司|集团|公司|银行|基金|资本))[，,]?\s*(?:位于|坐落于|总部在|设于|地处)\s*([\u4e00-\u9fff]{1,6}(?:省|市|区|县|州|国))', '位于', 'ORG', 'LOC'),
            # 籍贯
            (r'([\u4e00-\u9fff]{2,4}?)[，,]?\s*(?:出生于|生于|来自|籍贯)\s*([\u4e00-\u9fff]{1,6}(?:省|市|区|县|州|国))', '籍贯', 'PERSON', 'LOC'),
            # 收购
            (r'([\u4e00-\u9fffA-Za-z]{1,15}(?:有限公司|股份公司|集团|公司|银行|基金|资本))[，,]?\s*(?:收购|并购|兼并|买下|购入)\s*(?:了\s*)?([\u4e00-\u9fffA-Za-z]{1,15}(?:有限公司|股份公司|集团|公司|银行|基金|资本))', '收购', 'ORG', 'ORG'),
            # 投资
            (r'([\u4e00-\u9fffA-Za-z]{1,15}(?:有限公司|股份公司|集团|公司|银行|基金|资本))[，,]?\s*(?:投资|注资|领投)\s*(?:了\s*)?([\u4e00-\u9fffA-Za-z]{1,15}(?:有限公司|股份公司|集团|公司|银行|基金|资本))', '投资', 'ORG', 'ORG'),
            # 合作
            (r'([\u4e00-\u9fffA-Za-z]{1,15}(?:有限公司|股份公司|集团|公司|银行|基金|资本))[，,]?\s*(?:与|和)\s*([\u4e00-\u9fffA-Za-z]{1,15}(?:有限公司|股份公司|集团|公司|银行|基金|资本))\s*(?:合作|达成合作|签署合作|建立合作|战略合作)', '合作', 'ORG', 'ORG'),
            # 合作(兜底)
            (r'([\u4e00-\u9fffA-Za-z]{1,15}(?:有限公司|股份公司|集团|公司|银行|基金|资本))[，,]?\s*(?:与|和)\s*([\u4e00-\u9fffA-Za-z]{2,8}?)(?:\s+|在|，|,)\s*(?:\w+领域)?\s*(?:合作|达成合作|签署合作|建立合作|战略合作)', '合作', 'ORG', 'ORG'),
            # 联合发布
            (r'([\u4e00-\u9fffA-Za-z]{1,15}(?:有限公司|股份公司|集团|公司|银行|基金|资本))[，,]?\s*(?:与|和)\s*([\u4e00-\u9fffA-Za-z]{1,15}(?:有限公司|股份公司|集团|公司|银行|基金|资本))\s*(?:联合|共同)\s*(?:发布|开发|推出|研发)', '合作', 'ORG', 'ORG'),
            # 产品
            (r'([\u4e00-\u9fffA-Za-z]{1,15}(?:有限公司|股份公司|集团|公司|银行|基金|资本))[，,]?\s*(?:推出|发布|研发|开发|研制)\s*(?:了\s*)?([\u4e00-\u9fffA-Za-z0-9]{2,10}(?:大模型|操作系统|系统|平台|手机|汽车|芯片|产品))', '产品', 'ORG', 'PRODUCT'),
        ]

        relations: list[Relation] = []
        seen_triples: set[tuple] = set()

        for pattern, rel_type, h_type, t_type in text_level_patterns:
            for m in re.finditer(pattern, text):
                head_text = m.group(1)
                tail_text = m.group(2)
                triple = (head_text, rel_type, tail_text)
                if triple in seen_triples:
                    continue
                head_ent = Entity(text=head_text, label=h_type, start=m.start(1), end=m.end(1))
                tail_ent = Entity(text=tail_text, label=t_type, start=m.start(2), end=m.end(2))
                if not any(e.text == head_text for e in entities):
                    entities.append(head_ent)
                if not any(e.text == tail_text for e in entities):
                    entities.append(tail_ent)
                relations.append(Relation(
                    head=head_ent,
                    relation=rel_type,
                    tail=tail_ent,
                    confidence=0.85,
                    source="rule",
                ))
                seen_triples.add(triple)

        # 清洗：只保留关系引用到的实体
        used_entity_texts: set[str] = set()
        for r in relations:
            used_entity_texts.add(r.head.text)
            used_entity_texts.add(r.tail.text)
        entities[:] = [e for e in entities if e.text in used_entity_texts]

        return relations


# ============================================================
# 2. 基于 LLM Prompt 的关系抽取
# ============================================================

LLM_EXTRACTION_PROMPT = """你是一个知识图谱关系抽取专家。请从以下文本中抽取实体和关系三元组。

关系类型列表（也允许抽取不在列表中的关系）：
- 就职于: 人物 → 组织
- 创立: 人物 → 组织
- 位于: 组织/地点 → 地点
- 籍贯: 人物 → 地点
- 收购: 组织 → 组织
- 合作: 组织 → 组织
- 投资: 组织 → 组织
- 产品: 组织 → 产品
- 配偶: 人物 → 人物
- 子公司: 组织 → 组织
- 竞争: 组织 → 组织
- 毕业: 人物 → 组织
- 包含: 地点 → 地点

请以JSON格式输出，格式如下：
{{
  "entities": [
    {{"text": "实体文本", "label": "实体类型(PERSON/ORG/LOC/PRODUCT/DATE/EVENT)"}}
  ],
  "relations": [
    {{"head": "头实体", "relation": "关系类型", "tail": "尾实体", "confidence": 0.9}}
  ]
}}

注意：
1. 只抽取文本中明确表达的关系，不要推理
2. confidence范围0-1，表示关系的确信度
3. 如果文本中没有关系，返回空的entities和relations列表

待抽取文本：
{text}"""


class LLMExtractor:
    """基于大语言模型的关系抽取器"""

    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 model: str = "glm-4-flash"):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    def _call_llm(self, prompt: str) -> str:
        """调用LLM API（优先使用 zhipuai SDK，回退到 openai）"""
        import os

        _proxy_vars = ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']
        _saved = {v: os.environ.pop(v, None) for v in _proxy_vars}

        try:
            from zhipuai import ZhipuAI
            client = ZhipuAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2048,
            )
            return response.choices[0].message.content
        except ImportError:
            pass
        except Exception as e:
            logger.error(f"zhipuai调用失败: {e}")

        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url or "https://open.bigmodel.cn/api/paas/v4",
            )
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2048,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            return ""
        finally:
            for v, val in _saved.items():
                if val is not None:
                    os.environ[v] = val

    def extract(self, text: str) -> tuple[list[Entity], list[Relation]]:
        """使用LLM从文本中抽取实体和关系"""
        prompt = LLM_EXTRACTION_PROMPT.format(text=text)
        response = self._call_llm(prompt)

        if not response:
            return [], []

        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(response)
        except json.JSONDecodeError:
            logger.warning(f"LLM响应JSON解析失败: {response[:200]}")
            return [], []

        entities: list[Entity] = []
        for ent in data.get("entities", []):
            entities.append(Entity(
                text=ent.get("text", ""),
                label=ent.get("label", "UNKNOWN"),
            ))

        relations: list[Relation] = []
        for rel in data.get("relations", []):
            head_ent = None
            tail_ent = None
            head_text = rel.get("head", "")
            tail_text = rel.get("tail", "")

            for e in entities:
                if e.text == head_text and head_ent is None:
                    head_ent = e
                if e.text == tail_text and tail_ent is None:
                    tail_ent = e

            if head_ent and tail_ent:
                relations.append(Relation(
                    head=head_ent,
                    relation=rel.get("relation", "UNKNOWN"),
                    tail=tail_ent,
                    confidence=rel.get("confidence", 0.8),
                    source="llm",
                ))

        return entities, relations


# ============================================================
# 3. 混合抽取器（规则 + LLM）
# ============================================================

class HybridExtractor:
    """混合关系抽取器：规则匹配 + LLM，交叉验证提升准确率"""

    def __init__(self, llm_api_key: str | None = None, llm_base_url: str | None = None,
                 llm_model: str = "glm-4-flash", use_llm: bool = True):
        self.rule_extractor = RuleBasedExtractor()
        self.use_llm = use_llm
        if use_llm:
            self.llm_extractor = LLMExtractor(
                api_key=llm_api_key,
                base_url=llm_base_url,
                model=llm_model,
            )

    def extract(self, text: str) -> dict:
        """混合抽取：先规则，再LLM，合并去重"""
        rule_relations = self.rule_extractor.extract(text)
        rule_entities = self.rule_extractor._recognize_entities(text)

        for rel in rule_relations:
            if rel.head not in rule_entities:
                rule_entities.append(rel.head)
            if rel.tail not in rule_entities:
                rule_entities.append(rel.tail)

        result: dict = {
            "text": text,
            "entities": list(rule_entities),
            "relations": list(rule_relations),
            "method": "rule" if not self.use_llm else "hybrid",
        }

        if self.use_llm:
            try:
                llm_entities, llm_relations = self.llm_extractor.extract(text)

                existing_texts = {e.text for e in result["entities"]}
                for ent in llm_entities:
                    if ent.text not in existing_texts:
                        result["entities"].append(ent)
                        existing_texts.add(ent.text)

                existing_triples = {r.to_triple() for r in result["relations"]}
                for rel in llm_relations:
                    triple = rel.to_triple()
                    if triple in existing_triples:
                        for existing in result["relations"]:
                            if existing.to_triple() == triple:
                                existing.confidence = min(1.0, existing.confidence + 0.2)
                                existing.source = "hybrid"
                                break
                    else:
                        result["relations"].append(rel)

            except Exception as e:
                logger.error(f"LLM抽取失败，仅使用规则结果: {e}")

        # 转换为可序列化格式
        result["entities"] = [e.to_dict() for e in result["entities"]]
        result["relations"] = [r.to_dict() for r in result["relations"]]

        return result


# ============================================================
# 对外接口函数（与 entity_alignment / entity_disambiguation 风格一致）
# ============================================================

def extract_relations(
    text: str,
    method: str = "rule",
    llm_api_key: str | None = None,
    llm_base_url: str | None = None,
    llm_model: str = "glm-4-flash",
) -> dict:
    """
    从文本中抽取实体与关系三元组，返回结构化结果。

    method:
      - "rule": 纯规则匹配（默认，无需 API Key）
      - "llm":  纯大模型抽取
      - "hybrid": 规则 + LLM 混合
    """
    use_llm = method in ("llm", "hybrid") and bool(llm_api_key)
    extractor = HybridExtractor(
        use_llm=use_llm,
        llm_api_key=llm_api_key if use_llm else None,
        llm_base_url=llm_base_url if use_llm else None,
        llm_model=llm_model if use_llm else "",
    )
    return extractor.extract(text)


def batch_extract_relations(
    texts: list[str],
    method: str = "rule",
    llm_api_key: str | None = None,
    llm_base_url: str | None = None,
    llm_model: str = "glm-4-flash",
) -> dict:
    """批量从多个文本中抽取关系，合并去重后返回。"""
    all_entities: list[dict] = []
    all_relations: list[dict] = []
    seen_triples: set[tuple] = set()
    results: list[dict] = []

    for text in texts:
        if not text.strip():
            continue
        result = extract_relations(text, method, llm_api_key, llm_base_url, llm_model)
        results.append(result)

        for ent in result["entities"]:
            if not any(e["text"] == ent["text"] for e in all_entities):
                all_entities.append(ent)

        for rel in result["relations"]:
            triple = (rel["head"]["text"], rel["relation"], rel["tail"]["text"])
            if triple not in seen_triples:
                all_relations.append(rel)
                seen_triples.add(triple)

    return {
        "count": len(results),
        "results": results,
        "merged_entities": all_entities,
        "merged_relations": all_relations,
        "entity_count": len(all_entities),
        "relation_count": len(all_relations),
    }
