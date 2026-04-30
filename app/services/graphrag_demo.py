"""Neo4j-backed GraphRAG demo service."""

from __future__ import annotations

import hashlib
import math
import os
import re
from dataclasses import dataclass

from graph_db import GraphDBConfig, connect

try:
    from zai import ZhipuAiClient
except ImportError:  # pragma: no cover - optional import guard
    ZhipuAiClient = None


SAMPLE_QUESTIONS = [
    "GraphRAG 和普通向量检索有什么区别？",
    "微软的 GraphRAG 更适合回答哪类问题？",
    "Neo4j 在这个 demo 里承担什么角色？",
    "知识图谱如何帮助多跳检索？",
]


DEMO_DOCUMENTS = [
    {
        "document_id": "doc-graphrag-overview",
        "title": "GraphRAG Overview",
        "chunks": [
            {
                "chunk_id": "chunk-graphrag-1",
                "text": (
                    "GraphRAG 会先把文档中的实体、关系和主题社区抽取出来，"
                    "再把这些结构化结果用于检索和答案生成，因此它更擅长全局总结和多跳问题。"
                ),
                "mentions": ["ent-graphrag", "ent-entity", "ent-relation", "ent-community"],
            },
            {
                "chunk_id": "chunk-graphrag-2",
                "text": (
                    "与只返回相似文本块的朴素 RAG 相比，GraphRAG 能沿着图中的关系扩展上下文，"
                    "把分散在不同文档里的证据串起来。"
                ),
                "mentions": ["ent-graphrag", "ent-rag", "ent-relation", "ent-multihop"],
            },
        ],
    },
    {
        "document_id": "doc-microsoft-graphrag",
        "title": "Microsoft GraphRAG",
        "chunks": [
            {
                "chunk_id": "chunk-ms-1",
                "text": (
                    "微软开源的 GraphRAG 流程强调从非结构化文本中抽取实体、关系和 claim，"
                    "再做 community detection、社区摘要和多层级报告生成。"
                ),
                "mentions": ["ent-microsoft", "ent-graphrag", "ent-community", "ent-claim"],
            },
            {
                "chunk_id": "chunk-ms-2",
                "text": (
                    "这套方法特别适合需要全局理解的问题，例如一个研究主题有哪些关键群体、"
                    "它们之间如何关联，以及整体趋势是什么。"
                ),
                "mentions": ["ent-microsoft", "ent-graphrag", "ent-global-search", "ent-community"],
            },
        ],
    },
    {
        "document_id": "doc-neo4j-demo",
        "title": "Neo4j GraphRAG Demo",
        "chunks": [
            {
                "chunk_id": "chunk-neo4j-1",
                "text": (
                    "在 Neo4j 里做 GraphRAG，常见模式是把 Chunk、Entity 和它们的关系存成图，"
                    "查询时先做向量召回，再沿 MENTIONS 和 RELATED_TO 关系做图扩展。"
                ),
                "mentions": ["ent-neo4j", "ent-chunk", "ent-entity", "ent-vector", "ent-multihop"],
            },
            {
                "chunk_id": "chunk-neo4j-2",
                "text": (
                    "Neo4j 的价值在于把语义检索和图遍历放到同一个系统里，"
                    "这样更容易解释为什么命中了某些上下文，也更适合做多跳证据拼接。"
                ),
                "mentions": ["ent-neo4j", "ent-vector", "ent-multihop", "ent-explainability"],
            },
        ],
    },
]


DEMO_ENTITIES = [
    {
        "entity_id": "ent-graphrag",
        "name": "GraphRAG",
        "type": "Method",
        "description": "Graph-based retrieval augmented generation.",
    },
    {
        "entity_id": "ent-rag",
        "name": "Naive RAG",
        "type": "Method",
        "description": "Plain retrieval augmented generation over chunks.",
    },
    {
        "entity_id": "ent-neo4j",
        "name": "Neo4j",
        "type": "Database",
        "description": "Graph database used to store chunks, entities and edges.",
    },
    {
        "entity_id": "ent-microsoft",
        "name": "Microsoft",
        "type": "Organization",
        "description": "Maintainer of the open-source GraphRAG project.",
    },
    {
        "entity_id": "ent-community",
        "name": "Community Detection",
        "type": "Technique",
        "description": "Grouping entities into topical communities.",
    },
    {
        "entity_id": "ent-claim",
        "name": "Claim Extraction",
        "type": "Technique",
        "description": "Extracting explicit claims from documents.",
    },
    {
        "entity_id": "ent-global-search",
        "name": "Global Search",
        "type": "QueryMode",
        "description": "Question answering over broad corpus themes.",
    },
    {
        "entity_id": "ent-entity",
        "name": "Entity",
        "type": "GraphPrimitive",
        "description": "A real-world object represented in the graph.",
    },
    {
        "entity_id": "ent-relation",
        "name": "Relation",
        "type": "GraphPrimitive",
        "description": "An edge connecting entities or evidence.",
    },
    {
        "entity_id": "ent-vector",
        "name": "Vector Retrieval",
        "type": "Retriever",
        "description": "Embedding similarity search over chunks.",
    },
    {
        "entity_id": "ent-multihop",
        "name": "Multi-hop Retrieval",
        "type": "Retriever",
        "description": "Traversing multiple graph edges to gather evidence.",
    },
    {
        "entity_id": "ent-explainability",
        "name": "Explainability",
        "type": "Benefit",
        "description": "Ability to inspect retrieved paths and evidence.",
    },
    {
        "entity_id": "ent-chunk",
        "name": "Chunk",
        "type": "GraphPrimitive",
        "description": "A text segment stored with an embedding.",
    },
]


DEMO_RELATIONS = [
    ("ent-graphrag", "USES", "ent-entity"),
    ("ent-graphrag", "USES", "ent-relation"),
    ("ent-graphrag", "USES", "ent-community"),
    ("ent-graphrag", "ENABLES", "ent-global-search"),
    ("ent-graphrag", "IMPROVES", "ent-multihop"),
    ("ent-graphrag", "DIFFERS_FROM", "ent-rag"),
    ("ent-microsoft", "MAINTAINS", "ent-graphrag"),
    ("ent-neo4j", "SUPPORTS", "ent-vector"),
    ("ent-neo4j", "SUPPORTS", "ent-multihop"),
    ("ent-neo4j", "SUPPORTS", "ent-explainability"),
    ("ent-vector", "COMPLEMENTS", "ent-multihop"),
    ("ent-community", "SUPPORTS", "ent-global-search"),
    ("ent-claim", "SUPPORTS", "ent-graphrag"),
    ("ent-chunk", "CONNECTS_TO", "ent-entity"),
]


@dataclass
class ChunkCandidate:
    chunk_id: str
    document_id: str
    document_title: str
    text: str
    score: float
    entities: list[dict]
    related_entities: list[dict]


def _normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _char_ngrams(text: str, n: int = 2) -> list[str]:
    compact = re.sub(r"\s+", "", _normalize_text(text))
    if len(compact) <= n:
        return [compact] if compact else []
    return [compact[i : i + n] for i in range(len(compact) - n + 1)]


def _hash_embedding(text: str, dim: int = 32) -> list[float]:
    vector = [0.0] * dim
    grams = _char_ngrams(text, n=2) or [_normalize_text(text)]
    for gram in grams:
        digest = hashlib.sha256(gram.encode("utf-8")).digest()
        index = digest[0] % dim
        sign = 1.0 if digest[1] % 2 == 0 else -1.0
        weight = 1.0 + (digest[2] / 255.0)
        vector[index] += sign * weight

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [round(value / norm, 8) for value in vector]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True))


def _build_context_preview(chunks: list[ChunkCandidate]) -> str:
    sections: list[str] = []
    for chunk in chunks:
        entity_names = [entity["name"] for entity in chunk.entities]
        related_names = [entity["name"] for entity in chunk.related_entities]
        sections.append(
            f"[{chunk.document_title}] {chunk.text}\n"
            f"直接实体: {', '.join(entity_names) or '无'}\n"
            f"扩展实体: {', '.join(related_names) or '无'}"
        )
    return "\n\n".join(sections)


def _fallback_answer(query: str, chunks: list[ChunkCandidate]) -> str:
    if not chunks:
        return f"图里暂时没有召回到和“{query}”足够相关的内容。"

    top = chunks[0]
    entity_names = [entity["name"] for entity in top.entities[:4]]
    related_names = [entity["name"] for entity in top.related_entities[:4]]
    answer = f"基于 demo 图谱，最相关的证据来自《{top.document_title}》。它说明 {top.text}"
    if entity_names:
        answer += f" 这一跳直接命中的实体有 {', '.join(entity_names)}。"
    if related_names:
        answer += f" 继续沿图扩展还能看到 {', '.join(related_names)}，这就是 GraphRAG 比只看文本块更有用的地方。"
    return answer


def _llm_answer(query: str, context_preview: str) -> str | None:
    api_key = os.getenv("ZHIPUAI_API_KEY", "")
    if not api_key or ZhipuAiClient is None:
        return None

    client = ZhipuAiClient(api_key=api_key)
    model = os.getenv("MODEL", "glm-5.1")
    prompt = (
        "你是一个 GraphRAG demo 助手。请严格基于给定上下文，用简明中文回答用户问题。"
        "如果上下文不足，就明确说证据不足，不要编造。\n\n"
        f"问题：{query}\n\n"
        f"上下文：\n{context_preview}"
    )
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "只依据上下文回答。"},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return None


def _connect_graph():
    return connect(GraphDBConfig.from_env())


def demo_overview() -> dict:
    return {
        "name": "Neo4j GraphRAG Demo",
        "description": "向量召回 Chunk，再沿图扩展 Entity 和 RELATED_TO 关系，最后做回答拼接。",
        "graph_schema": {
            "nodes": ["DemoDocument", "DemoChunk", "DemoEntity"],
            "relationships": ["HAS_CHUNK", "MENTIONS", "RELATED_TO"],
        },
        "sample_questions": SAMPLE_QUESTIONS,
    }


def init_demo_graph(reset: bool = False) -> dict:
    db = _connect_graph()
    try:
        if reset:
            db.execute_write(
                """
                MATCH (n)
                WHERE n:DemoDocument OR n:DemoChunk OR n:DemoEntity
                DETACH DELETE n
                """
            )

        for entity in DEMO_ENTITIES:
            db.execute_write(
                """
                MERGE (e:DemoEntity {entity_id: $entity_id})
                SET e.name = $name,
                    e.type = $type,
                    e.description = $description
                """,
                entity,
            )

        for source_id, relation, target_id in DEMO_RELATIONS:
            db.execute_write(
                """
                MATCH (a:DemoEntity {entity_id: $source_id})
                MATCH (b:DemoEntity {entity_id: $target_id})
                MERGE (a)-[r:RELATED_TO {relation: $relation}]->(b)
                """,
                {
                    "source_id": source_id,
                    "target_id": target_id,
                    "relation": relation,
                },
            )

        for document in DEMO_DOCUMENTS:
            db.execute_write(
                """
                MERGE (d:DemoDocument {document_id: $document_id})
                SET d.title = $title
                """,
                {
                    "document_id": document["document_id"],
                    "title": document["title"],
                },
            )
            for position, chunk in enumerate(document["chunks"]):
                embedding = _hash_embedding(chunk["text"])
                db.execute_write(
                    """
                    MATCH (d:DemoDocument {document_id: $document_id})
                    MERGE (c:DemoChunk {chunk_id: $chunk_id})
                    SET c.text = $text,
                        c.position = $position,
                        c.embedding = $embedding
                    MERGE (d)-[:HAS_CHUNK]->(c)
                    """,
                    {
                        "document_id": document["document_id"],
                        "chunk_id": chunk["chunk_id"],
                        "text": chunk["text"],
                        "position": position,
                        "embedding": embedding,
                    },
                )
                for entity_id in chunk["mentions"]:
                    db.execute_write(
                        """
                        MATCH (c:DemoChunk {chunk_id: $chunk_id})
                        MATCH (e:DemoEntity {entity_id: $entity_id})
                        MERGE (c)-[:MENTIONS]->(e)
                        """,
                        {
                            "chunk_id": chunk["chunk_id"],
                            "entity_id": entity_id,
                        },
                    )

        document_count = db.node_count("DemoDocument")
        chunk_count = db.node_count("DemoChunk")
        entity_count = db.node_count("DemoEntity")
        relationship_count = (
            db.edge_count("HAS_CHUNK") + db.edge_count("MENTIONS") + db.edge_count("RELATED_TO")
        )
        return {
            "document_count": document_count,
            "chunk_count": chunk_count,
            "entity_count": entity_count,
            "relationship_count": relationship_count,
            "sample_questions": SAMPLE_QUESTIONS,
        }
    finally:
        db.close()


def _fetch_chunk_enrichment(db, chunk_id: str) -> ChunkCandidate | None:
    result = db.execute_read(
        """
        MATCH (d:DemoDocument)-[:HAS_CHUNK]->(c:DemoChunk {chunk_id: $chunk_id})
        OPTIONAL MATCH (c)-[:MENTIONS]->(e:DemoEntity)
        OPTIONAL MATCH (e)-[r:RELATED_TO]-(related:DemoEntity)
        RETURN
          d.document_id AS document_id,
          d.title AS document_title,
          c.chunk_id AS chunk_id,
          c.text AS text,
          collect(DISTINCT CASE
            WHEN e IS NULL THEN NULL
            ELSE {entity_id: e.entity_id, name: e.name, type: e.type}
          END) AS entities,
          collect(DISTINCT CASE
            WHEN related IS NULL THEN NULL
            ELSE {
              entity_id: related.entity_id,
              name: related.name,
              type: related.type,
              relation: r.relation
            }
          END) AS related_entities
        """,
        {"chunk_id": chunk_id},
    )
    if result.is_empty:
        return None

    record = result.records[0]
    entities = [item for item in record["entities"] if item]
    related_entities = [item for item in record["related_entities"] if item]
    return ChunkCandidate(
        chunk_id=record["chunk_id"],
        document_id=record["document_id"],
        document_title=record["document_title"],
        text=record["text"],
        score=0.0,
        entities=entities,
        related_entities=related_entities,
    )


def query_demo_graph(query: str, top_k: int = 3, max_related: int = 6) -> dict:
    db = _connect_graph()
    try:
        query_embedding = _hash_embedding(query)
        result = db.execute_read(
            """
            MATCH (d:DemoDocument)-[:HAS_CHUNK]->(c:DemoChunk)
            RETURN d.document_id AS document_id,
                   d.title AS document_title,
                   c.chunk_id AS chunk_id,
                   c.text AS text,
                   c.embedding AS embedding
            """
        )

        scored = []
        for record in result.records:
            score = _cosine_similarity(query_embedding, record["embedding"] or [])
            scored.append(
                {
                    "document_id": record["document_id"],
                    "document_title": record["document_title"],
                    "chunk_id": record["chunk_id"],
                    "text": record["text"],
                    "score": round(float(score), 4),
                }
            )
        scored.sort(key=lambda item: item["score"], reverse=True)
        top_chunks = scored[:top_k]

        enriched_chunks: list[ChunkCandidate] = []
        seen_entities: dict[str, dict] = {}
        for item in top_chunks:
            candidate = _fetch_chunk_enrichment(db, item["chunk_id"])
            if candidate is None:
                continue
            candidate.score = item["score"]
            candidate.related_entities = candidate.related_entities[:max_related]
            for entity in candidate.entities + candidate.related_entities:
                seen_entities[entity["entity_id"]] = entity
            enriched_chunks.append(candidate)

        context_preview = _build_context_preview(enriched_chunks)
        answer = _llm_answer(query, context_preview) or _fallback_answer(query, enriched_chunks)

        return {
            "query": query,
            "answer": answer,
            "method": "vector + graph expansion",
            "chunks": [
                {
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "document_title": chunk.document_title,
                    "text": chunk.text,
                    "score": chunk.score,
                    "entities": chunk.entities,
                    "related_entities": chunk.related_entities,
                }
                for chunk in enriched_chunks
            ],
            "retrieved_entities": list(seen_entities.values())[: max_related * top_k],
            "context_preview": context_preview,
        }
    finally:
        db.close()
