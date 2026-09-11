import { describe, expect, it } from "vitest";

import type { IndustryChainPanoramaQueryResponse } from "../../api/industryChainPanorama";
import {
  collectPanoramaTechnologyLabels,
  panoramaEdgeConfidence,
  selectPanoramaIndustryCenter,
} from "./panorama-graph";

function responseWithNodes(
  nodes: IndustryChainPanoramaQueryResponse["graph"]["nodes"],
  anchorId: string,
): IndustryChainPanoramaQueryResponse {
  return {
    taskName: "科技产业链全景图",
    input: { industry: "集成电路", anchorId },
    summary: {
      industry: "集成电路",
      totalNodes: nodes.length,
      totalEdges: 0,
      nodesByLabel: {},
      edgesByType: {},
    },
    layers: [],
    graph: { nodes, edges: [] },
    source: { requested: "all", actual: "graph-api", fallback: false },
    apiResultExample: {},
  };
}

describe("selectPanoramaIndustryCenter", () => {
  const technology = {
    id: "node_IC0007007",
    type: "IndustryNode",
    label: "集成电路设计",
    subtitle: null,
    data: {},
  };
  const chain = {
    id: "chain_IC0007",
    type: "IndustryChain",
    label: "集成电路",
    subtitle: null,
    data: {},
  };

  it("技术节点作为查询 anchor 时仍选择真实 IndustryChain 作为核心", () => {
    const response = responseWithNodes([technology, chain], technology.id);

    expect(selectPanoramaIndustryCenter(response, "集成电路")?.id).toBe(
      chain.id,
    );
  });

  it("不存在 IndustryChain 时不把技术 anchor 冒充为产业链核心", () => {
    const response = responseWithNodes([technology], technology.id);

    expect(selectPanoramaIndustryCenter(response, "集成电路")).toBeUndefined();
  });

  it("多个产业链节点时优先选择名称与查询产业一致的节点", () => {
    const otherChain = {
      ...chain,
      id: "chain_OTHER",
      label: "人工智能",
    };
    const response = responseWithNodes(
      [otherChain, chain, technology],
      technology.id,
    );

    expect(selectPanoramaIndustryCenter(response, "集成电路")?.id).toBe(
      chain.id,
    );
  });
});

describe("collectPanoramaTechnologyLabels", () => {
  it("合并技术分层与扩展子图中的技术 anchor，并按实体 ID 去重", () => {
    const response = responseWithNodes(
      [
        {
          id: "node_IC9901036",
          type: "IndustryNode",
          label: "无人机系统",
          subtitle: null,
          data: {},
        },
        {
          id: "node_IC9901007",
          type: "IndustryNode",
          label: "低空经济基建设施设备",
          subtitle: null,
          data: {},
        },
        {
          id: "org_1",
          type: "Organization",
          label: "低空经济企业",
          subtitle: null,
          data: {},
        },
      ],
      "node_IC9901036",
    );
    response.layers = [
      {
        key: "core_technology",
        title: "核心技术",
        total: 1,
        items: [
          {
            id: "node_IC9901007",
            label: "低空经济基建设施设备",
            type: "technology",
            subtitle: null,
            metric: null,
            metricValue: null,
          },
        ],
      },
    ];

    expect(collectPanoramaTechnologyLabels(response)).toEqual([
      "低空经济基建设施设备",
      "无人机系统",
    ]);
  });
});

describe("panoramaEdgeConfidence", () => {
  it("优先读取后端返回的标准置信度", () => {
    expect(
      panoramaEdgeConfidence({
        source: "org_1",
        target: "node_1",
        label: "BELONGS_TO_NODE",
        confidence: 0.9787,
        data: { chain_score: 85.5 },
      }),
    ).toBeCloseTo(0.9787);
  });

  it("兼容历史缓存响应中的 chain_score", () => {
    expect(
      panoramaEdgeConfidence({
        source: "org_1",
        target: "node_1",
        label: "BELONGS_TO_NODE",
        data: { chain_score: 85.5 },
      }),
    ).toBeCloseTo(0.855);
  });

  it("源关系没有置信度时不生成虚假数值", () => {
    expect(
      panoramaEdgeConfidence({
        source: "person_1",
        target: "org_1",
        label: "AFFILIATED_WITH",
        data: {},
      }),
    ).toBeUndefined();
  });
});
