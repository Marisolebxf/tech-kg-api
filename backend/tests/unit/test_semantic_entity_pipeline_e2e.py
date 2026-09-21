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
        if self.path == "/api/v1/ner/research/text":
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
        elif self.path == "/api/v1/concept-definition/text":
            data = {"definitions": [{"concept": "图神经网络", "definition": "处理图结构数据的神经网络。"}]}
        elif self.path == "/api/v1/research-question/text":
            data = {"structured_research_questions": ["如何提升图节点分类准确率？"]}
        elif self.path == "/api/v1/citation-intent/text":
            data = {"citation_intent_results": [{"intent": "引入研究方法"}]}
        elif self.path == "/api/v1/review/structured/texts":
            data = {"tree": {"title": payload["topic_or_keywords"]}}
        else:
            self._send({"code": 404, "message": "not found"}, 404)
            return
        self._send({"code": 0, "message": "success", "data": data, "meta": {}})


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
                    }
                ]
            }
        )
        self.assertEqual(result["failures"], [])
        self.assertEqual(result["stats"]["semanticApiCalls"], 4)
        self.assertEqual(len(result["entities"]), 1)
        props = result["entities"][0]["props"]
        self.assertEqual(props["name"], "图神经网络")
        self.assertEqual(props["entity_type"], "METHOD")
        self.assertEqual(props["definition"], "处理图结构数据的神经网络。")
        self.assertIn("如何提升图节点分类准确率", props["research_questions"])
        self.assertEqual(
            [call["path"] for call in _SemanticHandler.calls],
            [
                "/health",
                "/api/v1/ner/research/text",
                "/api/v1/concept-definition/text",
                "/api/v1/research-question/text",
            ],
        )


if __name__ == "__main__":
    unittest.main()
