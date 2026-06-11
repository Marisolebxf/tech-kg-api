"""实体消歧：句子中的 mention 链接到知识库实体（Demo 级实现）。"""

import numpy as np

from app.services.text_ngram import build_ngram_vocab, encode_texts, text_to_vector

KB = [
    {
        "id": "KB001",
        "name": "苹果公司",
        "aliases": ["苹果", "Apple", "Apple Inc"],
        "type": "科技公司",
        "description": "美国科技公司，1976年由乔布斯创立，总部库比蒂诺，产品包括iPhone MacBook iPad，CEO蒂姆库克，纳斯达克上市，市值万亿",
        "keywords": [
            "科技",
            "iPhone",
            "MacBook",
            "iPad",
            "乔布斯",
            "库克",
            "股价",
            "发布",
            "上市",
            "研发",
            "芯片",
            "App Store",
        ],
    },
    {
        "id": "KB002",
        "name": "苹果",
        "aliases": ["苹果", "苹果树", "苹果汁"],
        "type": "水果",
        "description": "蔷薇科苹果属植物果实，营养丰富含维生素，富含膳食纤维，有助消化，建议每天食用，产地山东陕西",
        "keywords": [
            "水果",
            "营养",
            "维生素",
            "食用",
            "健康",
            "膳食纤维",
            "消化",
            "种植",
            "采摘",
            "果园",
            "红富士",
        ],
    },
    {
        "id": "KB003",
        "name": "迈克尔·乔丹",
        "aliases": ["乔丹", "Michael Jordan", "飞人乔丹"],
        "type": "运动员",
        "description": "NBA篮球运动员，效力芝加哥公牛队，6次总冠军6次FMVP，被誉为史上最伟大篮球运动员，身穿23号球衣，Air Jordan品牌创始人",
        "keywords": [
            "NBA",
            "篮球",
            "公牛",
            "冠军",
            "球员",
            "运动",
            "总冠军",
            "23号",
            "进攻",
            "得分",
            "扣篮",
        ],
    },
    {
        "id": "KB004",
        "name": "约旦",
        "aliases": ["乔丹", "Jordan", "约旦王国"],
        "type": "国家",
        "description": "中东国家，首都安曼，阿拉伯语，伊斯兰教，与以色列巴勒斯坦叙利亚接壤，约旦河流经，佩特拉古城著名景点",
        "keywords": [
            "国家",
            "安曼",
            "中东",
            "阿拉伯",
            "签证",
            "旅游",
            "政府",
            "首都",
            "领土",
            "外交",
        ],
    },
    {
        "id": "KB005",
        "name": "长城",
        "aliases": ["长城", "万里长城", "Great Wall"],
        "type": "历史遗迹",
        "description": "中国古代军事防御工程，始建于秦朝秦始皇，全长超2万公里，世界文化遗产，八达岭慕田峪段最著名，是中华文明象征",
        "keywords": [
            "古代",
            "历史",
            "秦朝",
            "秦始皇",
            "防御",
            "军事",
            "文化遗产",
            "旅游景点",
            "修建",
            "遗址",
            "世界遗产",
        ],
    },
    {
        "id": "KB006",
        "name": "长城汽车",
        "aliases": ["长城", "长城汽车", "长城集团", "Great Wall Motors"],
        "type": "汽车公司",
        "description": "中国汽车制造商，旗下品牌哈弗坦克魏牌欧拉，SUV销量领先，总部河北保定，A股上市，出口多国",
        "keywords": [
            "汽车",
            "SUV",
            "哈弗",
            "坦克",
            "魏牌",
            "欧拉",
            "新能源",
            "销量",
            "上市",
            "制造",
            "车型",
            "发布",
        ],
    },
    {
        "id": "KB007",
        "name": "特斯拉公司",
        "aliases": ["特斯拉", "Tesla", "Tesla Inc"],
        "type": "电动车公司",
        "description": "美国电动汽车公司，CEO埃隆马斯克，产品包括Model 3 Model S Model X Cybertruck，超级充电桩，自动驾驶，2010年纳斯达克上市",
        "keywords": [
            "电动车",
            "Model 3",
            "马斯克",
            "自动驾驶",
            "充电",
            "续航",
            "新能源",
            "股价",
            "工厂",
            "纳斯达克",
        ],
    },
    {
        "id": "KB008",
        "name": "尼古拉·特斯拉",
        "aliases": ["特斯拉", "Nikola Tesla", "尼古拉特斯拉"],
        "type": "科学家",
        "description": "塞尔维亚裔美国科学家发明家，发明交流电系统，与爱迪生直流电之争，电磁感应，无线电传输先驱，晚年贫困潦倒",
        "keywords": [
            "科学家",
            "发明家",
            "交流电",
            "电磁",
            "发明",
            "物理",
            "爱迪生",
            "电力",
            "历史",
            "无线电",
            "感应",
        ],
    },
    {
        "id": "KB009",
        "name": "亚马逊公司",
        "aliases": ["亚马逊", "Amazon", "亚马逊电商"],
        "type": "电商公司",
        "description": "美国电商科技公司，创始人贝索斯，AWS云计算，Prime会员，Kindle，全球最大电商平台，纳斯达克上市，物流仓储自建",
        "keywords": [
            "电商",
            "购物",
            "平台",
            "下单",
            "物流",
            "快递",
            "AWS",
            "云计算",
            "会员",
            "Prime",
            "贝索斯",
            "购买",
        ],
    },
    {
        "id": "KB010",
        "name": "亚马逊河",
        "aliases": ["亚马逊", "Amazon River", "亚马孙河"],
        "type": "地理",
        "description": "南美洲最大河流，流经巴西秘鲁哥伦比亚，亚马逊热带雨林地球之肺，生物多样性最丰富地区，长度约6400公里",
        "keywords": [
            "河流",
            "雨林",
            "南美洲",
            "巴西",
            "热带",
            "生物多样性",
            "地球之肺",
            "森林",
            "生态",
            "保护",
            "自然",
        ],
    },
]

NIL_THRESHOLD = 0.30


def entity_to_text(entity: dict) -> str:
    aliases = " ".join(entity["aliases"])
    return f"{entity['name']} {aliases} {entity['type']} {entity['description']}"


def retrieve_top_k(
    query_vec: np.ndarray, index_vecs: np.ndarray, k: int = 5
) -> tuple[np.ndarray, np.ndarray]:
    sims = index_vecs @ query_vec
    top_k_idx = np.argsort(-sims)[:k]
    top_k_scores = sims[top_k_idx]
    return top_k_scores, top_k_idx


def context_rerank_score(sentence: str, mention: str, entity: dict) -> float:
    context_text = sentence.replace(mention, " ").lower()
    context_words = set(
        context_text.replace("，", " ")
        .replace("。", " ")
        .replace("、", " ")
        .replace("：", " ")
        .split()
    )
    context_words = {w for w in context_words if len(w) >= 2}

    entity_words: set[str] = set()
    entity_words.update(entity["keywords"])
    entity_words.update(entity["aliases"])
    entity_words.add(entity["type"])
    for token in entity["description"].replace("，", " ").replace("。", " ").split():
        if len(token) >= 2:
            entity_words.add(token)
    entity_words = {w.lower() for w in entity_words}

    if not context_words or not entity_words:
        return 0.0

    intersection = context_words & entity_words
    union = context_words | entity_words
    jaccard = len(intersection) / len(union)

    keyword_hits = sum(1 for kw in entity["keywords"] if kw in sentence)
    keyword_bonus = min(keyword_hits * 0.05, 0.2)

    return min(jaccard + keyword_bonus, 1.0)


def llm_judge(sentence: str, mention: str, entity: dict, rerank_score_val: float) -> dict:
    reasons: list[str] = []
    confidence = rerank_score_val

    hit_keywords = [kw for kw in entity["keywords"] if kw in sentence]
    if hit_keywords:
        confidence += 0.1 * min(len(hit_keywords), 3)
        reasons.append(f"上下文命中关键词：{hit_keywords[:3]}")

    type_signal = {
        "科技公司": ["发布", "股价", "产品", "上市", "研发", "芯片"],
        "水果": ["营养", "食用", "健康", "吃", "种植", "果"],
        "运动员": ["NBA", "比赛", "冠军", "球队", "赛季", "运动"],
        "国家": ["首都", "政府", "签证", "外交", "领土", "人口"],
        "历史遗迹": ["历史", "古代", "遗址", "文化遗产", "修建", "朝代"],
        "汽车公司": ["汽车", "SUV", "销量", "车型", "发布", "新能源"],
        "电动车公司": ["电动", "续航", "充电", "自动驾驶", "Model"],
        "科学家": ["发明", "科学", "物理", "实验", "研究", "历史"],
        "电商公司": ["购物", "下单", "物流", "快递", "购买", "平台"],
        "地理": ["河流", "雨林", "森林", "生态", "自然", "地理"],
    }
    type_hits = [w for w in type_signal.get(entity["type"], []) if w in sentence]
    if type_hits:
        confidence += 0.05 * min(len(type_hits), 2)
        reasons.append(f"类型语境匹配（{entity['type']}）：{type_hits[:2]}")

    confidence = min(confidence, 1.0)

    if confidence < NIL_THRESHOLD:
        verdict = "❓ Nil（置信度不足，触发人工复核 / 新实体入库）"
    elif confidence < 0.3:
        verdict = "⚠️ 低置信（需人工复核）"
    else:
        verdict = "✅ 链接成功"

    return {
        "verdict": verdict,
        "confidence": round(confidence, 3),
        "reasons": reasons,
        "is_nil": confidence < NIL_THRESHOLD,
    }


def disambiguate_entity(
    sentence: str,
    mention: str,
    kb: list[dict] | None = None,
    *,
    top_k: int = 5,
    ngram: int = 2,
) -> dict:
    """
    对单个 mention 在句子上下文中做实体链接，返回结构化结果。
    `kb` 为 None 或空列表时，使用内置示例知识库 KB。
    """
    kb = KB if not kb else kb
    kb_texts = [entity_to_text(e) for e in kb]
    all_texts = kb_texts + [mention]
    vocab = build_ngram_vocab(all_texts, n=ngram)
    kb_vecs = encode_texts(kb_texts, vocab, n=ngram)
    mention_vec = text_to_vector(mention, vocab, n=ngram)
    recall_scores, recall_indices = retrieve_top_k(mention_vec, kb_vecs, k=top_k)

    candidates: list[dict] = []
    for recall_rank, idx in enumerate(recall_indices, start=1):
        idx = int(idx)
        entity = kb[idx]
        vec_score = float(recall_scores[recall_rank - 1])
        ctx_score = context_rerank_score(sentence, mention, entity)
        candidates.append(
            {
                "kb_index": idx,
                "index": idx,
                "recall_rank": recall_rank,
                "entity_id": entity["id"],
                "name": entity["name"],
                "type": entity["type"],
                "entity": entity,
                "recall_score": vec_score,
                "context_rerank_score": ctx_score,
            }
        )
    # 精排分降序；同分按召回分降序，保证顺序稳定、可预期
    candidates.sort(key=lambda x: (-x["context_rerank_score"], -x["recall_score"], x["kb_index"]))
    for rank, c in enumerate(candidates, start=1):
        c["rank"] = rank

    best = candidates[0]
    judgment = llm_judge(sentence, mention, best["entity"], best["context_rerank_score"])
    linked_id: str | None = None if judgment["is_nil"] else best["entity_id"]

    return {
        "sentence": sentence,
        "mention": mention,
        "vocab_size": len(vocab),
        "embedding_dim": int(kb_vecs.shape[1]),
        "top_k": top_k,
        "candidates": candidates,
        "best_match": {
            "entity_id": best["entity_id"],
            "name": best["name"],
            "entity": best["entity"],
            "recall_score": best["recall_score"],
            "context_rerank_score": best["context_rerank_score"],
        },
        "judgment": judgment,
        "linked_entity_id": linked_id,
        "is_nil": judgment["is_nil"],
    }
