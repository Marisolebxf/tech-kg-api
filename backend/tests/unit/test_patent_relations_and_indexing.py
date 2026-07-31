import sys
from types import SimpleNamespace

from script.patent_indexing import HashedBM25, normalize_text, tokens


def test_hashed_bm25_roundtrip_and_normalization():
    model = HashedBM25(dimensions=128)
    model.observe("知识图谱 graph database")
    model.observe("图数据库")
    vector = model.encode("知识图谱")
    assert vector and all(0 <= key < 128 for key in vector)
    restored = HashedBM25.from_dict(model.to_dict())
    assert restored.encode("知识图谱") == vector
    assert normalize_text(" ＣＮ-1 A ") == "cn-1 a"
    assert "知识" in tokens("知识图谱")


def test_patent_collection_declares_exactly_eight_indexes():
    from script.build_patent_milvus_indexes import SCALAR_INDEXES

    assert len(SCALAR_INDEXES) == 6
    assert {field for field, _ in SCALAR_INDEXES} == {
        "publication_number",
        "application_number",
        "granted_number",
        "simple_family_number",
        "country_code",
        "source_table",
    }


def test_resume_rejects_changed_bm25_corpus(tmp_path):
    from script.build_patent_milvus_indexes import persist_bm25_state

    first = HashedBM25(dimensions=128)
    first.observe("专利 图谱")
    path = tmp_path / "patent_bm25.json"
    persist_bm25_state(first, path, resume=False)
    persist_bm25_state(first, path, resume=True)

    changed = HashedBM25(dimensions=128)
    changed.observe("完全不同的语料")
    try:
        persist_bm25_state(changed, path, resume=True)
    except RuntimeError as exc:
        assert "--rebuild" in str(exc)
    else:
        raise AssertionError("语料变化后不应混用旧BM25向量")


def test_only_patent_is_configured_for_indexing():
    from script.build_patent_milvus_indexes import PATENT_SPEC

    assert PATENT_SPEC.tag == "Patent"
    assert "Person" not in repr(PATENT_SPEC)
    assert "Organization" not in repr(PATENT_SPEC)


def test_dense_and_sparse_patent_fields_have_distinct_roles():
    from script.build_patent_milvus_indexes import PATENT_SPEC

    assert set(PATENT_SPEC.dense_fields) == {
        "title_zh",
        "title_en",
        "title_original",
        "abstract_zh",
        "keywords",
    }
    assert "application_number" not in PATENT_SPEC.dense_fields
    assert "application_number" in PATENT_SPEC.sparse_fields
    assert "main_ipcr" in PATENT_SPEC.sparse_fields


def test_local_embedder_defaults_to_m3e_small(monkeypatch):
    from script.build_patent_milvus_indexes import dense_embedder

    loaded = {}

    class Vectors(list):
        def tolist(self):
            return list(self)

    class FakeSentenceTransformer:
        def __init__(self, model_name, device):
            loaded.update(model_name=model_name, device=device)

        def get_sentence_embedding_dimension(self):
            return 512

        def encode(self, texts, **kwargs):
            loaded.update(encode_kwargs=kwargs)
            return Vectors([[0.0] * 512 for _ in texts])

    monkeypatch.delenv("PATENT_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("PATENT_LOCAL_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("PATENT_EMBEDDING_DIM", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )

    dim, encode = dense_embedder()
    vectors = encode(["中文专利", "English patent"])

    assert dim == 512
    assert loaded["model_name"] == "moka-ai/m3e-small"
    assert loaded["device"] == "cpu"
    assert loaded["encode_kwargs"]["normalize_embeddings"] is True
    assert len(vectors) == 2


def test_search_text_is_truncated_by_utf8_bytes():
    from script.patent_indexing import truncate_utf8

    result = truncate_utf8("专利" * 100, 101)
    assert len(result.encode("utf-8")) <= 101
    assert result.encode("utf-8").decode("utf-8") == result


def test_hybrid_search_reads_real_collection_fields_instead_of_metadata():
    from script.patent_hybrid_search import hybrid_search

    class Client:
        def hybrid_search(self, collection, requests, ranker, limit, output_fields):
            assert collection == "patent"
            assert "metadata" not in output_fields
            assert {"vid", "patent_id", "publication_number"} <= set(output_fields)
            return [[{"id": "fallback", "distance": 0.9, "entity": {"vid": "patent-real"}}]]

    matches = hybrid_search(Client(), "patent", [0.1, 0.2], {1: 0.5})
    assert matches[0].graph_vid == "patent-real"
