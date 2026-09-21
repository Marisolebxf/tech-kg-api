"""实体抽取脚本的真实服务端到端测试。

运行前必须设置 ``SEMANTIC_TOOLKIT_BASE_URL``。测试会真实调用健康检查、科研实体
识别、概念定义识别和研究问题识别接口，并校验脚本最终生成的图实体 JSON。
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND / "sdk"))
sys.path.insert(0, str(BACKEND))

from kg_sdk import reset_current_context  # noqa: E402
from script.semantic_research_entity_extract import extract_research_entities  # noqa: E402


@unittest.skipUnless(
    os.getenv("SEMANTIC_TOOLKIT_BASE_URL"),
    "未设置 SEMANTIC_TOOLKIT_BASE_URL，跳过真实服务端到端测试",
)
class SemanticEntityPipelineLiveTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_current_context()

    def tearDown(self) -> None:
        reset_current_context()

    def test_entity_extraction_pipeline_against_live_service(self) -> None:
        title = os.getenv("SEMANTIC_E2E_TITLE", "图神经网络节点分类研究")
        text = os.getenv(
            "SEMANTIC_E2E_TEXT",
            "本文提出一种基于图神经网络的文本属性图节点分类方法，"
            "使用注意力机制融合节点文本特征与邻居结构信息，以提高分类准确率。",
        )
        result = extract_research_entities(
            {
                "rows": [
                    {
                        "id": "live-e2e-paper-1",
                        "title": title,
                        "abstract": text,
                    }
                ]
            }
        )

        print(
            "\nSEMANTIC_LIVE_E2E_RESULT="
            + json.dumps(result, ensure_ascii=False, indent=2, default=str)
        )

        self.assertEqual(result["stats"]["rows"], 1)
        self.assertEqual(result["stats"]["semanticApiCalls"], 4)
        self.assertEqual(result["failures"], [], f"真实服务调用失败：{result['failures']}")
        self.assertGreater(len(result["entities"]), 0, "真实服务未抽取到任何科研实体")
        self.assertEqual(result["stats"]["entities"], len(result["entities"]))
        self.assertEqual(result["stats"]["failed"], 0)

        for entity in result["entities"]:
            self.assertTrue(entity["id"].startswith("semantic_entity_"))
            props = entity["props"]
            self.assertEqual(props["id"], entity["id"])
            self.assertTrue(props["name"])
            self.assertTrue(props["entity_type"])
            self.assertEqual(props["source_document_id"], "live-e2e-paper-1")
            self.assertEqual(props["source_document_title"], title)
            self.assertIsInstance(json.loads(props["research_questions"]), list)


if __name__ == "__main__":
    unittest.main(verbosity=2)
