"""kg_sdk 语义工具 + 实体抽取脚本的本地 HTTP 端到端测试。"""

from __future__ import annotations

import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND / "sdk"))
sys.path.insert(0, str(BACKEND))

from kg_sdk import SemanticToolkitClient, reset_current_context  # noqa: E402

from script.semantic_research_entity_extract import extract_research_entities  # noqa: E402


class _SemanticHandler(BaseHTTPRequestHandler):
    calls: list[dict] = []

    def log_message(self, format, *args):  # noqa: A002
        return

    def _send(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        self.calls.append(
            {"method": "GET", "path": self.path, "api_key": self.headers.get("X-API-Key")}
        )
        if self.path == "/health":
            self._send({"status": "ok"})
        elif self.path == "/api/v1/catalog":
            self._send({"code": 0, "message": "success", "data": {"features": []}})
        else:
            self._send({"code": 404, "message": "not found"}, 404)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        self.calls.append(
            {
                "method": "POST",
                "path": self.path,
                "api_key": self.headers.get("X-API-Key"),
                "payload": payload,
            }
        )
        data: dict
        meta: dict = {}
        if self.path == "/api/v1/ner/general/text":
            data = {
                "entity_results": [
                    {"text": "OpenAI", "type": "ORGANIZATION", "confidence": 0.97}
                ]
            }
            meta = {"record_id": f"general-{len(self.calls)}"}
        elif self.path == "/api/v1/ner/research/text":
            data = {
                "entity_results": [
                    {
                        "text": "GNN",
                        "type": "METHOD",
                        "confidence": 0.98,
                        "standard_names": {"zh": "图神经网络", "en": "Graph Neural Network"},
                    }
                ]
            }
            meta = {"record_id": f"research-{len(self.calls)}"}
        elif self.path == "/api/v1/ner/domain/text":
            data = {
                "entity_results": [
                    {"text": "Transformer", "type": "MODEL", "confidence": 0.96}
                ],
                "selected_domain": payload.get("domain") or "计算机",
            }
            meta = {"record_id": f"domain-{len(self.calls)}"}
        elif self.path == "/api/v1/concept-definition/text":
            data = {"definitions": [{"concept": "图神经网络", "definition": "处理图结构数据的神经网络。"}]}
        elif self.path == "/api/v1/research-question/text":
            data = {"structured_research_questions": ["如何提升图节点分类准确率？"]}
        elif self.path == "/api/v1/citation-intent/text":
            data = {"citation_intent_results": [{"intent": "引入研究方法"}]}
        elif self.path == "/api/v1/citation-sentiment/text":
            data = {"citation_sentiment_results": [{"sentiment": "支持"}]}
        elif self.path.startswith("/api/v1/move/"):
            data = {"moves": [{"move_type": "方法", "text": "提出新方法"}]}
        elif self.path.startswith("/api/v1/classify/"):
            data = {
                "classifications": [
                    {"clc_code": "TP18", "clc_name": "自动化基础理论"}
                ]
            }
        elif self.path.startswith("/api/v1/keywords/"):
            data = {
                "keywords": [
                    {"keyword": "图神经网络", "normalized_term": "图神经网络", "confidence": 0.95}
                ]
            }
        elif self.path == "/api/v1/relation/from-ner-record":
            data = {
                "relation_triples": [
                    {"subject": "图神经网络", "relation": "用于", "object": "节点分类"}
                ]
            }
        elif self.path == "/api/v1/cluster/deep/texts":
            data = {
                "clusters": [
                    {
                        "cluster_id": "cluster-1",
                        "topic_name": "图学习",
                        "representative_terms": ["图神经网络", "节点分类"],
                    }
                ]
            }
        elif self.path == "/api/v1/cluster-labels/generate":
            data = {"labels": [{"cluster_id": "cluster-1", "label": "图学习方法"}]}
        elif self.path == "/api/v1/review/structured/texts":
            data = {"tree": {"title": payload["topic_or_keywords"]}}
        else:
            self._send({"code": 404, "message": "not found"}, 404)
            return
        self._send({"code": 0, "message": "success", "data": data, "meta": meta})


class SemanticEntityPipelineE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _SemanticHandler.calls = []
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _SemanticHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self) -> None:
        _SemanticHandler.calls.clear()
        os.environ["KG_SCRIPT_CTX"] = json.dumps(
            {
                "semantic": {
                    "base_url": f"{self.base_url}/api/v1",
                    "api_key": "e2e-key",
                    "timeout": 5,
                }
            }
        )
        reset_current_context()

    def tearDown(self) -> None:
        os.environ.pop("KG_SCRIPT_CTX", None)
        reset_current_context()

    def test_client_tools_over_real_http(self) -> None:
        client = SemanticToolkitClient(f"{self.base_url}/api/v1", "e2e-key", timeout=5)
        self.assertEqual(client.health()["status"], "ok")
        self.assertEqual(client.catalog()["code"], 0)
        entities = client.entities_of(client.research_entities("节点分类", "GNN用于节点分类"))
        self.assertEqual(entities[0]["standard_names"]["zh"], "图神经网络")
        self.assertEqual(
            client.definitions_of(client.concept_definitions("图神经网络用于图数据"))[0][
                "concept"
            ],
            "图神经网络",
        )
        self.assertEqual(
            client.questions_of(client.research_questions("节点分类", "如何提高准确率"))[0],
            "如何提升图节点分类准确率？",
        )
        self.assertTrue(all(call["api_key"] == "e2e-key" for call in _SemanticHandler.calls))

    def test_entity_extraction_pipeline_over_real_http(self) -> None:
        result = extract_research_entities(
            {
                "rows": [
                    {
                        "id": "paper-1",
                        "title": "图神经网络节点分类",
                        "abstract": "本文使用GNN提升图节点分类准确率。",
                        "language": "zh",
                        "document_type": "paper",
                        "domain": "计算机",
                        "reference_entries": "[1] 图学习研究",
                    },
                    {
                        "id": "paper-2",
                        "title": "Graph neural network classification",
                        "abstract": "We use a GNN for accurate node classification.",
                        "language": "en",
                        "document_type": "paper",
                        "domain": "computer",
                    },
                    {
                        "id": "project-1",
                        "title": "图学习基金项目",
                        "content": "本项目研究图神经网络方法与节点分类。",
                        "language": "zh",
                        "document_type": "fund",
                        "domain": "计算机",
                    },
                    {
                        "id": "report-1",
                        "title": "Graph learning report",
                        "content": "This report studies graph learning applications.",
                        "language": "en",
                        "document_type": "report",
                        "domain": "computer",
                    },
                ],
            }
        )
        self.assertEqual(result["failures"], [])
        self.assertEqual(result["stats"]["rows"], 4)
        self.assertEqual(result["stats"]["validRows"], 4)
        self.assertGreaterEqual(len(result["entities"]), 8)
        self.assertGreaterEqual(len(result["relations"]), 1)

        names = {entity["props"]["name"] for entity in result["entities"]}
        self.assertIn("图神经网络", names)
        self.assertIn("自动化基础理论", names)
        self.assertIn("图学习", names)
        self.assertIn("图学习方法", names)
        gnn = next(
            entity for entity in result["entities"] if entity["props"]["name"] == "图神经网络"
        )
        self.assertIn("如何提升图节点分类准确率", gnn["props"]["research_questions"])

        capability_stats = result["stats"]["capabilities"]
        self.assertEqual(len(capability_stats), 18)
        self.assertTrue(
            all(values["succeeded"] >= 1 for values in capability_stats.values()),
            capability_stats,
        )
        self.assertNotIn("structured_review", capability_stats)

        paths = {call["path"] for call in _SemanticHandler.calls}
        expected_paths = {
            "/health",
            "/api/v1/move/abstract/zh/text",
            "/api/v1/move/abstract/en/text",
            "/api/v1/move/fund/zh/text",
            "/api/v1/classify/clc/zh/text",
            "/api/v1/classify/clc/en/text",
            "/api/v1/classify/domain/text",
            "/api/v1/keywords/zh/text",
            "/api/v1/keywords/en/text",
            "/api/v1/research-question/text",
            "/api/v1/citation-sentiment/text",
            "/api/v1/citation-intent/text",
            "/api/v1/concept-definition/text",
            "/api/v1/ner/general/text",
            "/api/v1/ner/research/text",
            "/api/v1/ner/domain/text",
            "/api/v1/relation/from-ner-record",
            "/api/v1/cluster/deep/texts",
            "/api/v1/cluster-labels/generate",
        }
        self.assertEqual(paths, expected_paths)
        self.assertNotIn("/api/v1/review/structured/texts", paths)


if __name__ == "__main__":
    unittest.main()
