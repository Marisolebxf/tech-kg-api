"""真实语义计算服务冒烟测试；配置服务地址后才执行。"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND / "sdk"))

from kg_sdk import get_semantic_client  # noqa: E402


@unittest.skipUnless(
    os.getenv("SEMANTIC_TOOLKIT_BASE_URL"),
    "未设置 SEMANTIC_TOOLKIT_BASE_URL，跳过真实服务测试",
)
class SemanticToolkitLiveTest(unittest.TestCase):
    def test_health_and_entity_flow(self) -> None:
        client = get_semantic_client(timeout=60)
        self.assertIsNotNone(client)
        assert client is not None
        health = client.health()
        self.assertIn(str(health.get("status", "")).casefold(), {"ok", "healthy", "success"})

        response = client.research_entities(
            "图神经网络节点分类研究",
            "本文提出一种图神经网络模型，用于文本属性图节点分类。",
        )
        self.assertGreater(len(client.entities_of(response)), 0)

        definitions = client.concept_definitions(
            "图神经网络是一类直接处理图结构数据的深度学习模型。"
        )
        self.assertIsInstance(client.definitions_of(definitions), list)


if __name__ == "__main__":
    unittest.main()
