"""实体对齐：两知识图谱节点互相对齐（Demo 级实现）。"""

import numpy as np

from app.services.text_ngram import build_ngram_vocab, encode_texts, text_to_vector

# 默认示例数据（中文 KG / 英文 KG）
KG_A = [
    {
        "id": "A001",
        "name": "苹果公司",
        "attributes": {
            "成立时间": "1976年",
            "总部": "库比蒂诺",
            "创始人": "史蒂夫·乔布斯",
            "行业": "科技",
        },
        "relations": [("生产", "iPhone"), ("生产", "MacBook"), ("CEO", "蒂姆·库克")],
    },
    {
        "id": "A002",
        "name": "微软",
        "attributes": {
            "成立时间": "1975年",
            "总部": "雷德蒙德",
            "创始人": "比尔·盖茨",
            "行业": "科技",
        },
        "relations": [("生产", "Windows"), ("生产", "Office"), ("CEO", "萨提亚·纳德拉")],
    },
    {
        "id": "A003",
        "name": "谷歌",
        "attributes": {
            "成立时间": "1998年",
            "总部": "山景城",
            "创始人": "拉里·佩奇",
            "行业": "互联网",
        },
        "relations": [("生产", "Chrome"), ("生产", "Android"), ("母公司", "Alphabet")],
    },
    {
        "id": "A004",
        "name": "亚马逊",
        "attributes": {
            "成立时间": "1994年",
            "总部": "西雅图",
            "创始人": "杰夫·贝索斯",
            "行业": "电商",
        },
        "relations": [("旗下", "AWS"), ("旗下", "Prime Video"), ("CEO", "安迪·贾西")],
    },
    {
        "id": "A005",
        "name": "特斯拉",
        "attributes": {
            "成立时间": "2003年",
            "总部": "奥斯汀",
            "创始人": "埃隆·马斯克",
            "行业": "电动车",
        },
        "relations": [("生产", "Model S"), ("生产", "Model 3"), ("CEO", "埃隆·马斯克")],
    },
    {
        "id": "A006",
        "name": "脸书",
        "attributes": {
            "成立时间": "2004年",
            "总部": "门洛帕克",
            "创始人": "马克·扎克伯格",
            "行业": "社交媒体",
        },
        "relations": [("旗下", "Instagram"), ("旗下", "WhatsApp"), ("母公司", "Meta")],
    },
    {
        "id": "A007",
        "name": "英伟达",
        "attributes": {
            "成立时间": "1993年",
            "总部": "圣克拉拉",
            "创始人": "黄仁勋",
            "行业": "半导体",
        },
        "relations": [("生产", "GeForce"), ("生产", "CUDA"), ("CEO", "黄仁勋")],
    },
]

KG_B = [
    {
        "id": "B001",
        "name": "Apple Inc.",
        "attributes": {
            "founded": "1976",
            "headquarters": "Cupertino",
            "founder": "Steve Jobs",
            "industry": "Technology",
        },
        "relations": [("produces", "iPhone"), ("produces", "MacBook"), ("CEO", "Tim Cook")],
    },
    {
        "id": "B002",
        "name": "Microsoft Corporation",
        "attributes": {
            "founded": "1975",
            "headquarters": "Redmond",
            "founder": "Bill Gates",
            "industry": "Technology",
        },
        "relations": [("produces", "Windows"), ("produces", "Office"), ("CEO", "Satya Nadella")],
    },
    {
        "id": "B003",
        "name": "Google LLC",
        "attributes": {
            "founded": "1998",
            "headquarters": "Mountain View",
            "founder": "Larry Page",
            "industry": "Internet",
        },
        "relations": [("produces", "Chrome"), ("produces", "Android"), ("parent", "Alphabet")],
    },
    {
        "id": "B004",
        "name": "Amazon.com Inc.",
        "attributes": {
            "founded": "1994",
            "headquarters": "Seattle",
            "founder": "Jeff Bezos",
            "industry": "E-commerce",
        },
        "relations": [("subsidiary", "AWS"), ("subsidiary", "Prime Video"), ("CEO", "Andy Jassy")],
    },
    {
        "id": "B005",
        "name": "Tesla Inc.",
        "attributes": {
            "founded": "2003",
            "headquarters": "Austin",
            "founder": "Elon Musk",
            "industry": "Electric vehicles",
        },
        "relations": [("produces", "Model S"), ("produces", "Model 3"), ("CEO", "Elon Musk")],
    },
    {
        "id": "B006",
        "name": "Meta Platforms",
        "attributes": {
            "founded": "2004",
            "headquarters": "Menlo Park",
            "founder": "Mark Zuckerberg",
            "industry": "Social media",
        },
        "relations": [("owns", "Instagram"), ("owns", "WhatsApp"), ("formerly", "Facebook")],
    },
    {
        "id": "B007",
        "name": "NVIDIA Corporation",
        "attributes": {
            "founded": "1993",
            "headquarters": "Santa Clara",
            "founder": "Jensen Huang",
            "industry": "Semiconductors",
        },
        "relations": [("produces", "GeForce"), ("produces", "CUDA"), ("CEO", "Jensen Huang")],
    },
    {
        "id": "B008",
        "name": "Intel Corporation",
        "attributes": {
            "founded": "1968",
            "headquarters": "Santa Clara",
            "founder": "Gordon Moore",
            "industry": "Semiconductors",
        },
        "relations": [("produces", "Core i9"), ("CEO", "Pat Gelsinger")],
    },
]

CROSS_LINGUAL_MAP = {
    "苹果": "apple",
    "公司": "inc corporation",
    "微软": "microsoft",
    "谷歌": "google",
    "亚马逊": "amazon",
    "特斯拉": "tesla",
    "脸书": "facebook meta",
    "英伟达": "nvidia",
    "成立时间": "founded",
    "总部": "headquarters",
    "创始人": "founder",
    "行业": "industry",
    "科技": "technology",
    "电商": "e-commerce",
    "互联网": "internet",
    "电动车": "electric vehicles",
    "半导体": "semiconductors",
    "社交媒体": "social media",
    "生产": "produces",
    "旗下": "subsidiary owns",
    "母公司": "parent",
    "乔布斯": "jobs",
    "盖茨": "gates",
    "库比蒂诺": "cupertino",
    "雷德蒙德": "redmond",
    "山景城": "mountain view",
    "西雅图": "seattle",
    "奥斯汀": "austin",
    "门洛帕克": "menlo park",
    "圣克拉拉": "santa clara",
    "黄仁勋": "jensen huang",
}


def entity_to_text(entity: dict) -> str:
    parts = [entity["name"]]
    for k, v in entity["attributes"].items():
        parts.append(f"{k}:{v}")
    for rel, tail in entity.get("relations", []):
        parts.append(f"{rel}:{tail}")
    return " ".join(parts)


def retrieve_top_k(
    query_vecs: np.ndarray, index_vecs: np.ndarray, k: int = 3
) -> tuple[np.ndarray, np.ndarray]:
    sim_matrix = query_vecs @ index_vecs.T
    top_k_indices = np.argsort(-sim_matrix, axis=1)[:, :k]
    top_k_scores = np.take_along_axis(sim_matrix, top_k_indices, axis=1)
    return top_k_scores, top_k_indices


def translate_to_common(text: str) -> str:
    result = text.lower()
    for zh, en in CROSS_LINGUAL_MAP.items():
        result = result.replace(zh, " " + en + " ")
    return result


def rerank_score(text_a: str, text_b: str) -> float:
    common_a = set(translate_to_common(text_a).split())
    common_b = set(text_b.lower().split())
    if not common_a or not common_b:
        return 0.0
    intersection = common_a & common_b
    union = common_a | common_b
    return len(intersection) / len(union)


def llm_judge(entity_a: dict, entity_b: dict, score: float) -> dict:
    reasons: list[str] = []
    confidence = score

    year_a = entity_a["attributes"].get("成立时间", "").replace("年", "").strip()
    year_b = entity_b["attributes"].get("founded", "").strip()
    if year_a and year_b and year_a == year_b:
        confidence += 0.2
        reasons.append(f"成立年份一致（{year_a}）")

    tails_a = {tail.lower() for _, tail in entity_a.get("relations", [])}
    tails_b = {tail.lower() for _, tail in entity_b.get("relations", [])}
    overlap = tails_a & tails_b
    if overlap:
        confidence += 0.1 * len(overlap)
        reasons.append(f"共同关联实体：{overlap}")

    industry_a = entity_a["attributes"].get("行业", "").lower()
    industry_b = entity_b["attributes"].get("industry", "").lower()
    industry_map = {
        "科技": "technology",
        "互联网": "internet",
        "电商": "e-commerce",
        "电动车": "electric vehicles",
        "半导体": "semiconductors",
        "社交媒体": "social media",
    }
    if industry_map.get(industry_a, "") in industry_b:
        confidence += 0.15
        reasons.append(f"行业匹配（{industry_a} ↔ {industry_b}）")

    confidence = min(confidence, 1.0)
    verdict = "✅ 对齐" if confidence >= 0.5 else "❌ 不对齐"

    return {
        "verdict": verdict,
        "confidence": round(confidence, 3),
        "reasons": reasons,
    }


def align_knowledge_graphs(
    kg_a: list[dict] | None = None,
    kg_b: list[dict] | None = None,
    *,
    top_k: int = 3,
    ngram: int = 2,
) -> dict:
    """
    对两个知识图谱做实体对齐，返回结构化结果（无打印副作用）。
    `kg_a` / `kg_b` 为 None 或空列表时，使用内置示例图谱 KG_A / KG_B。
    """
    kg_a = KG_A if not kg_a else kg_a
    kg_b = KG_B if not kg_b else kg_b

    texts_a = [entity_to_text(e) for e in kg_a]
    texts_b = [entity_to_text(e) for e in kg_b]
    all_texts = texts_a + texts_b
    vocab = build_ngram_vocab(all_texts, n=ngram)
    embeddings_a = encode_texts(texts_a, vocab, n=ngram)
    embeddings_b = encode_texts(texts_b, vocab, n=ngram)
    scores, indices = retrieve_top_k(embeddings_a, embeddings_b, k=top_k)

    items: list[dict] = []
    aligned_pairs: list[dict] = []

    for i, entity_a in enumerate(kg_a):
        candidates: list[dict] = []
        for rank, j in enumerate(indices[i]):
            j = int(j)
            entity_b = kg_b[j]
            vec_score = float(scores[i][rank])
            rerank = rerank_score(texts_a[i], texts_b[j])
            candidates.append(
                {
                    "index_b": j,
                    "entity_b_id": entity_b["id"],
                    "entity_b_name": entity_b["name"],
                    "entity_b": entity_b,
                    "vector_score": vec_score,
                    "rerank_score": rerank,
                }
            )
        candidates.sort(key=lambda x: -x["rerank_score"])

        best = candidates[0]
        judgment = llm_judge(entity_a, best["entity_b"], best["rerank_score"])
        aligned = "✅" in judgment["verdict"]

        row = {
            "entity_a_id": entity_a["id"],
            "entity_a_name": entity_a["name"],
            "entity_a": entity_a,
            "text_a": texts_a[i],
            "candidates": candidates,
            "best_match": {
                "entity_b_id": best["entity_b_id"],
                "entity_b_name": best["entity_b_name"],
                "entity_b": best["entity_b"],
                "vector_score": best["vector_score"],
                "rerank_score": best["rerank_score"],
            },
            "judgment": judgment,
            "aligned": aligned,
        }
        items.append(row)

        if aligned:
            aligned_pairs.append(
                {
                    "id_a": entity_a["id"],
                    "id_b": best["entity_b_id"],
                    "name_a": entity_a["name"],
                    "name_b": best["entity_b_name"],
                    "confidence": judgment["confidence"],
                }
            )

    return {
        "vocab_size": len(vocab),
        "embedding_dim": int(embeddings_a.shape[1]),
        "top_k": top_k,
        "count_a": len(kg_a),
        "count_b": len(kg_b),
        "aligned_count": len(aligned_pairs),
        "pairs": aligned_pairs,
        "details": items,
    }
