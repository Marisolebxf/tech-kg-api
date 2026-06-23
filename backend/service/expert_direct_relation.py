from __future__ import annotations

from datetime import datetime
from typing import Any

from service.base_module import KGModuleScaffoldService


EXPERT_DIRECT_RELATION_FALLBACK_DATA: list[dict[str, Any]] = [
    {
        "key": "expert-fallback-01",
        "label": "科技专家直接关系（张明远 / 李佳宁）",
        "last_test_time": "2026-07-23 11:00:00",
        "expert_a": {"id": "fallback_zhangmingyuan", "name": "张明远", "title": "研究员"},
        "expert_b": {"id": "fallback_lijianing", "name": "李佳宁", "title": "副研究员"},
        "relation_type": "直接关系",
        "institution": "中国科学院自动化研究所",
        "directions": ["知识图谱", "机器学习"],
        "duration": "",
        "achievements": [],
        "api_example": {
            "relation_type": "expert_direct_relation",
            "relation_subtype": "direct",
            "expert_a": {"name": "张明远", "title": "研究员"},
            "expert_b": {"name": "李佳宁", "title": "副研究员"},
            "institution": "中国科学院自动化研究所",
            "reasons": ["同机构", "共论文"],
            "relation_strength": 82,
            "relation_summary": "同机构 + 共论文",
        },
    },
    {
        "key": "expert-fallback-02",
        "label": "科技专家直接关系（李佳宁 / 周欣怡）",
        "last_test_time": "2026-07-23 11:10:00",
        "expert_a": {"id": "fallback_lijianing", "name": "李佳宁", "title": "副研究员"},
        "expert_b": {"id": "fallback_zhouxinyi", "name": "周欣怡", "title": "教授"},
        "relation_type": "直接关系",
        "institution": "智能决策联合实验室",
        "directions": ["智能决策", "知识工程"],
        "duration": "",
        "achievements": [],
        "api_example": {
            "relation_type": "expert_direct_relation",
            "relation_subtype": "direct",
            "expert_a": {"name": "李佳宁", "title": "副研究员"},
            "expert_b": {"name": "周欣怡", "title": "教授"},
            "institution": "智能决策联合实验室",
            "reasons": ["共项目", "Co-Author"],
            "relation_strength": 79,
            "relation_summary": "共项目 + Co-Author",
        },
    },
    {
        "key": "expert-fallback-03",
        "label": "科技专家直接关系（周欣怡 / 赵文博）",
        "last_test_time": "2026-08-01 15:40:00",
        "expert_a": {"id": "fallback_zhouxinyi", "name": "周欣怡", "title": "教授"},
        "expert_b": {"id": "fallback_zhaowenbo", "name": "赵文博", "title": "副教授"},
        "relation_type": "直接关系",
        "institution": "北京航空航天大学计算机学院",
        "directions": ["智能决策", "大模型"],
        "duration": "",
        "achievements": [],
        "api_example": {
            "relation_type": "expert_direct_relation",
            "relation_subtype": "direct",
            "expert_a": {"name": "周欣怡", "title": "教授"},
            "expert_b": {"name": "赵文博", "title": "副教授"},
            "institution": "北京航空航天大学计算机学院",
            "reasons": ["同机构", "共专利", "共论文"],
            "relation_strength": 91,
            "relation_summary": "同机构 + 共专利 + 共论文",
        },
    },
    {
        "key": "expert-fallback-04",
        "label": "科技专家直接关系（赵文博 / 陈星宇）",
        "last_test_time": "2026-08-05 10:20:00",
        "expert_a": {"id": "fallback_zhaowenbo", "name": "赵文博", "title": "副教授"},
        "expert_b": {"id": "fallback_chenxingyu", "name": "陈星宇", "title": "研究员"},
        "relation_type": "直接关系",
        "institution": "清华大学智能产业研究院",
        "directions": ["大模型", "产业智能"],
        "duration": "",
        "achievements": [],
        "api_example": {
            "relation_type": "expert_direct_relation",
            "relation_subtype": "direct",
            "expert_a": {"name": "赵文博", "title": "副教授"},
            "expert_b": {"name": "陈星宇", "title": "研究员"},
            "institution": "清华大学智能产业研究院",
            "reasons": ["共项目", "共论文"],
            "relation_strength": 84,
            "relation_summary": "共项目 + 共论文",
        },
    },
    {
        "key": "expert-fallback-05",
        "label": "科技专家直接关系（陈星宇 / 刘成）",
        "last_test_time": "2026-08-09 09:15:00",
        "expert_a": {"id": "fallback_chenxingyu", "name": "陈星宇", "title": "研究员"},
        "expert_b": {"id": "fallback_liucheng", "name": "刘成", "title": "高级工程师"},
        "relation_type": "直接关系",
        "institution": "国家智能计算实验室",
        "directions": ["算力调度", "智能计算"],
        "duration": "",
        "achievements": [],
        "api_example": {
            "relation_type": "expert_direct_relation",
            "relation_subtype": "direct",
            "expert_a": {"name": "陈星宇", "title": "研究员"},
            "expert_b": {"name": "刘成", "title": "高级工程师"},
            "institution": "国家智能计算实验室",
            "reasons": ["Co-Author", "共专利"],
            "relation_strength": 80,
            "relation_summary": "Co-Author + 共专利",
        },
    },
    {
        "key": "expert-fallback-06",
        "label": "科技专家直接关系（刘成 / 张明远）",
        "last_test_time": "2026-08-12 14:00:00",
        "expert_a": {"id": "fallback_liucheng", "name": "刘成", "title": "高级工程师"},
        "expert_b": {"id": "fallback_zhangmingyuan", "name": "张明远", "title": "研究员"},
        "relation_type": "直接关系",
        "institution": "国家智能计算实验室",
        "directions": ["智能计算", "知识图谱"],
        "duration": "",
        "achievements": [],
        "api_example": {
            "relation_type": "expert_direct_relation",
            "relation_subtype": "direct",
            "expert_a": {"name": "刘成", "title": "高级工程师"},
            "expert_b": {"name": "张明远", "title": "研究员"},
            "institution": "国家智能计算实验室",
            "reasons": ["共项目", "同机构"],
            "relation_strength": 78,
            "relation_summary": "共项目 + 同机构",
        },
    },
]


class ExpertDirectRelationService(KGModuleScaffoldService):
    module_code = "expert_direct_relation"

    def build_relation_response(
        self,
        data_source: str = "all",
        expert_a_id: str | None = None,
        expert_b_id: str | None = None,
        institution: str | None = None,
        relation_type: str = "direct",
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        query_params = {
            "dataSource": (data_source or "all").strip().lower(),
            "expertAId": (expert_a_id or "").strip(),
            "expertBId": (expert_b_id or "").strip(),
            "institution": (institution or "").strip(),
            "relationType": (relation_type or "direct").strip().lower(),
            "startTime": (start_time or "").strip(),
            "endTime": (end_time or "").strip(),
        }
        scenarios = self._build_scenarios(query_params["dataSource"], query_params["relationType"])
        scenarios = self._filter_scenarios(scenarios, query_params)
        for scenario in scenarios:
            scenario["api_example"]["query_params"] = dict(query_params)
        return {"scenarios": scenarios}

    def _build_scenarios(self, data_source: str, relation_type: str) -> list[dict[str, Any]]:
        normalized_source = (data_source or "all").strip().lower()
        normalized_relation = (relation_type or "direct").strip().lower()

        scenarios = [self._build_scenario(item) for item in EXPERT_DIRECT_RELATION_FALLBACK_DATA]

        if normalized_source in {"all", "graph", "real"}:
            scenarios = list(scenarios)

        if normalized_relation in {"two_hop", "three_hop"} and len(scenarios) > 1:
            scenarios = self._select_hop_scenarios(scenarios, normalized_relation)

        return scenarios

    @staticmethod
    def _scenario_complexity_score(scenario: dict[str, Any]) -> tuple[int, float]:
        api_example = scenario.get("api_example") or {}
        reasons = api_example.get("reasons") or []
        if not isinstance(reasons, list):
            reasons = [reasons]
        reason_count = len([reason for reason in reasons if str(reason).strip()])
        relation_strength = float(api_example.get("relation_strength") or 0.0)
        return reason_count, relation_strength

    def _select_hop_scenarios(self, scenarios: list[dict[str, Any]], relation_type: str) -> list[dict[str, Any]]:
        ranked = []
        for index, scenario in enumerate(scenarios):
            reason_count, relation_strength = self._scenario_complexity_score(scenario)
            complexity_score = float(reason_count * 10 + relation_strength)
            ranked.append((complexity_score, reason_count, relation_strength, index, scenario))

        ranked.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
        pivot = max(1, len(ranked) // 2)
        if relation_type == "two_hop":
            selected = ranked[:pivot]
        else:
            selected = ranked[pivot:] or ranked[-pivot:]
        return [item[4] for item in selected]

    def _filter_scenarios(
        self,
        scenarios: list[dict[str, Any]],
        query_params: dict[str, str],
    ) -> list[dict[str, Any]]:
        expert_a_query = query_params.get("expertAId", "")
        expert_b_query = query_params.get("expertBId", "")
        institution_query = query_params.get("institution", "")
        relation_query = query_params.get("relationType", "direct")
        start_dt = self._parse_query_datetime(query_params.get("startTime", ""))
        end_dt = self._parse_query_datetime(query_params.get("endTime", ""))

        def get_row_value(scenario: dict[str, Any], row_key: str) -> Any:
            for key, value in scenario.get("detail_rows", []):
                if key == row_key:
                    return value
            return ""

        def match_expert(scenario: dict[str, Any], side: str, query: str) -> bool:
            if not query or query == "全部":
                return True
            query_text = query.lower()
            expert = scenario.get("api_example", {}).get("expert_a" if side == "a" else "expert_b", {})
            row_name = str(get_row_value(scenario, "专家 A" if side == "a" else "专家 B"))
            graph_nodes = [node for node in scenario.get("graph", {}).get("nodes", []) if node.get("kind") == ("expertA" if side == "a" else "expertB")]
            values = [row_name, str(expert.get("name", "")), str(expert.get("id", ""))]
            values.extend([node.get("id", "") for node in graph_nodes])
            values.extend([node.get("subtitle", "") for node in graph_nodes])
            return any(query_text in str(value).lower() for value in values if value)

        def match_institution(scenario: dict[str, Any]) -> bool:
            if not institution_query or institution_query == "全部":
                return True
            query_text = institution_query.lower()
            values = [
                str(scenario.get("api_example", {}).get("institution", "")),
                str(get_row_value(scenario, "直接关系")),
            ]
            values.extend([node.get("subtitle", "") for node in scenario.get("graph", {}).get("nodes", []) if node.get("kind") == "institution"])
            return any(query_text in str(value).lower() for value in values if value)

        def match_relation(scenario: dict[str, Any]) -> bool:
            normalized = (relation_query or "direct").strip().lower()
            if normalized in {"", "all", "direct", "two_hop", "three_hop"}:
                return True
            reasons = scenario.get("api_example", {}).get("reasons") or get_row_value(scenario, "判定依据") or []
            if not isinstance(reasons, list):
                reasons = [reasons]
            return any(normalized in str(reason).lower() for reason in reasons)

        def match_time(scenario: dict[str, Any]) -> bool:
            test_dt = self._parse_query_datetime(scenario.get("last_test_time", ""))
            if not test_dt:
                return True
            if start_dt and test_dt < start_dt:
                return False
            if end_dt and test_dt > end_dt:
                return False
            return True

        return [
            scenario
            for scenario in scenarios
            if match_expert(scenario, "a", expert_a_query)
            and match_expert(scenario, "b", expert_b_query)
            and match_institution(scenario)
            and match_relation(scenario)
            and match_time(scenario)
        ]

    @staticmethod
    def _parse_query_datetime(raw_value: str | None) -> datetime | None:
        if not raw_value:
            return None
        value = raw_value.strip()
        if not value:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    @staticmethod
    def _build_scenario(item: dict[str, Any]) -> dict[str, Any]:
        expert_a = item["expert_a"]
        expert_b = item["expert_b"]
        institution = item["institution"]
        relation_type = item["relation_type"]
        directions = item.get("directions", [])
        achievements = item.get("achievements", [])
        graph = ExpertDirectRelationService._build_relation_graph(
            expert_a=expert_a,
            expert_b=expert_b,
            relation_type=relation_type,
            institution=institution,
            directions=directions,
            duration=item.get("duration", ""),
            achievements=achievements,
            expert_a_id=str(expert_a.get("id") or expert_a.get("name") or "expertA"),
            expert_b_id=str(expert_b.get("id") or expert_b.get("name") or "expertB"),
        )
        detail_rows = [
            ["专家 A", expert_a["name"]],
            ["专家 A 职称", expert_a["title"]],
            ["专家 B", expert_b["name"]],
            ["专家 B 职称", expert_b["title"]],
            ["关系类型", f"科技专家直接关系 / {relation_type}"],
            ["直接关系", institution],
            ["判定依据", item.get("api_example", {}).get("reasons", [])],
            ["关系强度", item.get("api_example", {}).get("relation_strength", 0)],
            ["关系摘要", item.get("api_example", {}).get("relation_summary", "")],
        ]
        return {
            "key": item["key"],
            "label": item["label"],
            "last_test_time": item["last_test_time"],
            "graph": graph,
            "detail_rows": detail_rows,
            "api_example": dict(item["api_example"]),
        }

    @staticmethod
    def _build_relation_graph(
        expert_a: dict[str, str],
        expert_b: dict[str, str],
        relation_type: str,
        institution: str,
        directions: list[str],
        duration: str,
        achievements: list[dict[str, Any]],
        expert_a_id: str = "expertA",
        expert_b_id: str = "expertB",
    ) -> dict[str, Any]:
        institution_id = f"institution-{institution}"
        return {
            "width": 860,
            "height": 640,
            "nodes": [
                {
                    "id": expert_a_id,
                    "kind": "expertA",
                    "x": 90,
                    "y": 140,
                    "icon": "👤",
                    "title": f"专家A：{expert_a['name']}",
                    "subtitle": expert_a["title"],
                    "desc": "",
                    "chips": list(directions[:2]),
                    "achievements": achievements,
                },
                {
                    "id": expert_b_id,
                    "kind": "expertB",
                    "x": 550,
                    "y": 140,
                    "icon": "👤",
                    "title": f"专家B：{expert_b['name']}",
                    "subtitle": expert_b["title"],
                    "desc": "",
                    "chips": list(directions[2:4]),
                    "achievements": achievements,
                },
                {
                    "id": institution_id,
                    "kind": "institution",
                    "x": 270,
                    "y": 340,
                    "icon": "🏛",
                    "title": "直接关系",
                    "subtitle": institution,
                    "desc": duration,
                    "chips": [],
                    "achievements": [],
                },
            ],
            "edges": [
                {
                    "type": "curve",
                    "from_": [276, 196],
                    "to": [550, 196],
                    "stroke": "#a355ec",
                    "marker": "#a355ec",
                    "width": 4,
                    "label": relation_type,
                    "label_x": 398,
                    "label_y": 178,
                    "label_color": "#8f52db",
                },
                {
                    "type": "curve",
                    "from_": [220, 240],
                    "c1": [250, 290],
                    "c2": [330, 335],
                    "to": [402, 392],
                    "stroke": "#6ca2ff",
                    "marker": "#6ca2ff",
                    "width": 4,
                    "label": "直连",
                    "label_x": 275,
                    "label_y": 320,
                    "label_color": "#6b8fd6",
                },
                {
                    "type": "curve",
                    "from_": [640, 240],
                    "c1": [620, 290],
                    "c2": [540, 335],
                    "to": [458, 392],
                    "stroke": "#6ca2ff",
                    "marker": "#6ca2ff",
                    "width": 4,
                    "label": "直连",
                    "label_x": 555,
                    "label_y": 320,
                    "label_color": "#6b8fd6",
                },
            ],
        }
