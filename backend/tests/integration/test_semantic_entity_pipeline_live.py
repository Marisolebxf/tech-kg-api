"""18 类语义 API 抽取脚本的真实服务端到端测试。

默认服务地址为 ``http://10.50.183.56:8080/api/v1``。这些测试会产生真实的语义
计算请求，因此默认不随普通测试集运行；在能访问该内网地址的机器上执行：

    RUN_SEMANTIC_LIVE_TESTS=1 uv run pytest -q \
      tests/integration/test_semantic_entity_pipeline_live.py -v

可通过 ``SEMANTIC_TOOLKIT_BASE_URL``、``SEMANTIC_TOOLKIT_API_KEY`` 和
``SEMANTIC_E2E_TIMEOUT`` 覆盖服务地址、鉴权信息和单请求超时。
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from typing import Any

import pytest

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND / "sdk"))
sys.path.insert(0, str(BACKEND))

from kg_sdk import SemanticToolkitClient, reset_current_context  # noqa: E402

from script.semantic_research_entity_extract import extract_research_entities  # noqa: E402

LIVE_BASE_URL = os.getenv(
    "SEMANTIC_TOOLKIT_BASE_URL",
    "http://10.50.183.56:8080/api/v1",
)
LIVE_TIMEOUT = float(os.getenv("SEMANTIC_E2E_TIMEOUT", "600"))
RUN_LIVE = os.getenv("RUN_SEMANTIC_LIVE_TESTS", "").casefold() in {"1", "true", "yes"}
pytestmark = pytest.mark.external


@unittest.skipUnless(
    RUN_LIVE,
    "设置 RUN_SEMANTIC_LIVE_TESTS=1 后运行 18 类真实语义 API 端到端测试",
)
class SemanticEntityPipelineLiveTest(unittest.TestCase):
    """每个测试均经过 ``extract_research_entities`` 调用真实语义服务。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.api_key = os.getenv("SEMANTIC_TOOLKIT_API_KEY")
        client = SemanticToolkitClient(
            LIVE_BASE_URL,
            cls.api_key,
            timeout=min(LIVE_TIMEOUT, 30),
        )
        try:
            health = client.health()
        except Exception as exc:  # noqa: BLE001 - 外部服务不可达时应明确跳过
            raise unittest.SkipTest(
                f"语义服务不可达：{LIVE_BASE_URL}；{type(exc).__name__}: {exc}"
            ) from exc
        if str(health.get("status", "ok")).casefold() not in {"ok", "healthy", "success"}:
            raise unittest.SkipTest(f"语义服务健康检查未通过：{health}")

    def setUp(self) -> None:
        self.previous_context = os.environ.get("KG_SCRIPT_CTX")
        semantic: dict[str, Any] = {
            "base_url": LIVE_BASE_URL,
            "timeout": LIVE_TIMEOUT,
        }
        if self.api_key:
            semantic["api_key"] = self.api_key
        os.environ["KG_SCRIPT_CTX"] = json.dumps({"semantic": semantic}, ensure_ascii=False)
        reset_current_context()

    def tearDown(self) -> None:
        if self.previous_context is None:
            os.environ.pop("KG_SCRIPT_CTX", None)
        else:
            os.environ["KG_SCRIPT_CTX"] = self.previous_context
        reset_current_context()

    @staticmethod
    def _zh_row(record_id: str = "live-zh-paper") -> dict[str, Any]:
        return {
            "id": record_id,
            "title": "深度学习驱动的桥梁损伤识别研究",
            "abstract": (
                "桥梁结构健康监测是保障基础设施安全的重要手段。"
                "本文提出一种基于卷积神经网络的损伤识别方法，并在公开数据集上验证。"
                "实验结果表明该方法能够提高识别准确率，研究证明其具有应用价值。"
            ),
            "language": "zh",
            "document_type": "paper",
        }

    @staticmethod
    def _en_row(record_id: str = "live-en-paper") -> dict[str, Any]:
        return {
            "id": record_id,
            "title": "Graph Neural Networks for Bridge Damage Detection",
            "abstract": (
                "Bridge health monitoring is important for infrastructure safety. "
                "We propose a graph neural network method and evaluate it on a public dataset. "
                "The results improve detection accuracy and demonstrate practical value."
            ),
            "language": "en",
            "document_type": "paper",
        }

    @staticmethod
    def _fund_row() -> dict[str, Any]:
        return {
            "id": "live-fund-project",
            "title": "面向桥梁健康监测的图神经网络关键技术研究",
            "content": (
                "立项依据：桥梁损伤的早期识别具有重要意义。"
                "研究目标：构建面向复杂结构的图神经网络模型。"
                "研究内容：研究多源传感数据融合、图结构学习与损伤定位。"
                "研究方案：完成数据采集、模型训练、对比实验和工程验证。"
                "预期成果：形成算法、数据集和示范应用。"
            ),
            "language": "zh",
            "document_type": "fund",
        }

    @staticmethod
    def _citation_row() -> dict[str, Any]:
        return {
            "id": "live-citation-paper",
            "title": "图神经网络节点分类研究",
            "content": (
                "已有研究[1]提出卷积神经网络方法，并显著提高了节点分类准确率。"
                "然而，该方法在小样本条件下仍存在一定局限。"
            ),
            "reference_entries": "[1] Zhang et al. Graph Neural Networks. 2024.",
            "language": "zh",
            "document_type": "paper",
        }

    @classmethod
    def _cluster_rows(cls) -> list[dict[str, Any]]:
        rows = [
            cls._zh_row("live-cluster-1"),
            {
                **cls._zh_row("live-cluster-2"),
                "title": "图神经网络节点分类方法",
                "abstract": "本文研究图神经网络、注意力机制与文本属性图节点分类。",
            },
            {
                **cls._zh_row("live-cluster-3"),
                "title": "多源传感数据融合与故障诊断",
                "abstract": "本文研究多源传感器数据融合、故障诊断和工业设备预测维护。",
            },
            {
                **cls._zh_row("live-cluster-4"),
                "title": "材料性能预测与机器学习",
                "abstract": "本文利用机器学习模型预测新材料性能并分析关键影响因素。",
            },
        ]
        return rows

    def _run_capabilities(
        self,
        capabilities: list[str],
        rows: list[dict[str, Any]],
        *,
        expected: list[str] | None = None,
    ) -> dict[str, Any]:
        result = extract_research_entities(
            {
                "capabilities": capabilities,
                "rows": rows,
            }
        )
        expected = expected or capabilities
        for capability in expected:
            stats = result["stats"]["capabilities"][capability]
            related_failures = [
                failure
                for failure in result["failures"]
                if failure.get("capability") == capability
            ]
            self.assertGreaterEqual(
                stats["attempted"],
                1,
                f"{capability} 未发起真实请求：{json.dumps(result, ensure_ascii=False)}",
            )
            self.assertGreaterEqual(
                stats["succeeded"],
                1,
                f"{capability} 未成功：{json.dumps(related_failures, ensure_ascii=False)}",
            )
            self.assertEqual(stats["failed"], 0, related_failures)
        self.assertNotIn("structured_review", result["stats"]["capabilities"])
        return result

    def test_01_zh_abstract_move(self) -> None:
        self._run_capabilities(["zh_abstract_move"], [self._zh_row()])

    def test_02_en_abstract_move(self) -> None:
        self._run_capabilities(["en_abstract_move"], [self._en_row()])

    def test_03_fund_move(self) -> None:
        self._run_capabilities(["fund_move"], [self._fund_row()])

    def test_04_zh_classify(self) -> None:
        self._run_capabilities(["zh_classify"], [self._zh_row()])

    def test_05_en_classify(self) -> None:
        self._run_capabilities(["en_classify"], [self._en_row()])

    def test_06_domain_classify(self) -> None:
        row = {**self._zh_row(), "domain": "28"}
        self._run_capabilities(["domain_classify"], [row])

    def test_07_zh_keyword(self) -> None:
        result = self._run_capabilities(["zh_keyword"], [self._zh_row()])
        self.assertGreater(len(result["entities"]), 0, "中文关键词接口未生成实体")

    def test_08_en_keyword(self) -> None:
        result = self._run_capabilities(["en_keyword"], [self._en_row()])
        self.assertGreater(len(result["entities"]), 0, "英文关键词接口未生成实体")

    def test_09_research_question(self) -> None:
        result = self._run_capabilities(["research_question"], [self._zh_row()])
        data = result["semanticResults"][0]["capabilities"]["research_question"]
        self.assertTrue(data, "研究问题接口返回 data 为空")

    def test_10_citation_sentiment(self) -> None:
        self._run_capabilities(["citation_sentiment"], [self._citation_row()])

    def test_11_citation_intent(self) -> None:
        self._run_capabilities(["citation_intent"], [self._citation_row()])

    def test_12_concept_definition(self) -> None:
        result = self._run_capabilities(["concept_definition"], [self._zh_row()])
        self.assertGreater(len(result["entities"]), 0, "概念定义接口未生成概念实体")

    def test_13_general_ner(self) -> None:
        row = {
            "id": "live-general-ner",
            "title": "人工智能学术活动",
            "text": "张伟在北京参加清华大学举办的人工智能论坛。",
            "language": "zh",
        }
        result = self._run_capabilities(["general_ner"], [row])
        self.assertGreater(len(result["entities"]), 0, "通用实体接口未生成实体")

    def test_14_research_ner(self) -> None:
        result = self._run_capabilities(["research_ner"], [self._zh_row()])
        self.assertGreater(len(result["entities"]), 0, "科研实体接口未生成实体")

    def test_15_domain_ner(self) -> None:
        row = {**self._zh_row(), "domain": "计算机"}
        result = self._run_capabilities(["domain_ner"], [row])
        self.assertGreater(len(result["entities"]), 0, "专业领域实体接口未生成实体")

    def test_16_relation_extract(self) -> None:
        result = self._run_capabilities(
            ["research_ner", "relation_extract"],
            [self._zh_row()],
            expected=["research_ner", "relation_extract"],
        )
        self.assertGreater(len(result["relations"]), 0, "实体关系接口未生成关系")

    def test_17_deep_cluster(self) -> None:
        result = self._run_capabilities(["deep_cluster"], self._cluster_rows())
        self.assertIn("deep_cluster", result["batchResults"])

    def test_18_cluster_label(self) -> None:
        result = self._run_capabilities(
            ["deep_cluster", "cluster_label"],
            self._cluster_rows(),
            expected=["deep_cluster", "cluster_label"],
        )
        self.assertIn("cluster_label", result["batchResults"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
