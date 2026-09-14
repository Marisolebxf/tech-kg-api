import { describe, expect, it } from "vitest";

import type { IndustryChainPanoramaQueryResponse } from "../../api/industryChainPanorama";
import {
  collectPanoramaEntities,
  collectPanoramaIndustryChainLabels,
  collectPanoramaTechnologyLabels,
  panoramaEdgeConfidence,
  panoramaLayerConfidence,
  panoramaNodeRelationSummaries,
  panoramaProvenanceCards,
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

describe("collectPanoramaIndustryChainLabels", () => {
  it("合并后端统计的产业链与子图中的 IndustryChain 节点并去重", () => {
    const response = responseWithNodes(
      [
        {
          id: "chain_IC0007",
          type: "IndustryChain",
          label: "集成电路",
          subtitle: null,
          data: {},
        },
      ],
      "",
    );
    response.summary.industry = null;
    response.summary.industryChains = ["集成电路", "低空经济"];

    expect(collectPanoramaIndustryChainLabels(response)).toEqual([
      "集成电路",
      "低空经济",
    ]);
  });

  it("后端未返回产业链且子图没有 IndustryChain 节点时返回空列表", () => {
    const response = responseWithNodes(
      [
        {
          id: "node_IC0007007",
          type: "IndustryNode",
          label: "集成电路设计",
          subtitle: null,
          data: {},
        },
      ],
      "",
    );

    expect(collectPanoramaIndustryChainLabels(response)).toEqual([]);
  });
});

describe("collectPanoramaEntities", () => {
  function entityResponse(): IndustryChainPanoramaQueryResponse {
    const response = responseWithNodes(
      [
        {
          id: "chain_IC0007",
          type: "IndustryChain",
          label: "集成电路",
          subtitle: null,
          sourceTable: "dwd_industry_chain",
          data: {},
        },
        {
          id: "org_1",
          type: "Organization",
          label: "华南智能芯片",
          subtitle: null,
          data: {},
        },
      ],
      "",
    );
    response.layers = [
      {
        key: "leading_expert",
        title: "领军专家",
        total: 2,
        items: [
          {
            id: "person_1",
            label: "张明远",
            type: "expert",
            subtitle: null,
            metric: "置信度 0.92",
            metricValue: 92,
            sourceTable: "dwd_scholar",
          },
          // 与子图节点同 id：去重后只保留子图实体（子图在前）。
          {
            id: "org_1",
            label: "华南智能芯片（分层）",
            type: "enterprise",
            subtitle: null,
            metric: null,
            metricValue: null,
          },
        ],
      },
    ];
    return response;
  }

  it("合并子图节点与分层实体并按 id 去重，子图实体在前", () => {
    const entities = collectPanoramaEntities(entityResponse());

    expect(entities.map((entity) => entity.id)).toEqual([
      "chain_IC0007",
      "org_1",
      "person_1",
    ]);
    // 同 id 实体保留子图版本（label 无「分层」后缀）。
    expect(entities[1].label).toBe("华南智能芯片");
    expect(entities[2].layerKey).toBe("leading_expert");
  });

  it("分层实体按指标换算置信度，子图实体取相邻边最大值，孤立节点回退默认值", () => {
    const response = entityResponse();
    // org_1 两条相邻边：chain_score 85.5 → 0.855、AFFILIATED_WITH 推导 0.85，取最大。
    response.graph.edges = [
      {
        source: "chain_IC0007",
        target: "org_1",
        label: "BELONGS_TO_NODE",
        data: { chain_score: 85.5 },
      },
      {
        source: "chain_IC0007",
        target: "org_1",
        label: "AFFILIATED_WITH",
        data: {},
      },
    ];
    const entities = collectPanoramaEntities(response);

    expect(entities[0].confidence).toBeCloseTo(0.855);
    expect(entities[1].confidence).toBeCloseTo(0.855);
    // person_1 是分层实体：按指标换算（92 → 0.92），不受相邻边影响。
    expect(entities[2].confidence).toBeCloseTo(0.92);
    // 孤立子图节点（无相邻边）回退默认值。
    response.graph.nodes.push({
      id: "iso_1",
      type: "Keyword",
      label: "孤立关键词",
      subtitle: null,
      data: {},
    });
    const isolated = collectPanoramaEntities(response).find(
      (entity) => entity.id === "iso_1",
    );
    expect(isolated?.confidence).toBeCloseTo(0.8);
    expect(panoramaLayerConfidence(null)).toBe(0.75);
    expect(panoramaLayerConfidence(30)).toBeCloseTo(0.4);
  });
});

describe("panoramaNodeRelationSummaries", () => {
  function relationResponse(): IndustryChainPanoramaQueryResponse {
    const response = responseWithNodes(
      [
        {
          id: "chain_1",
          type: "IndustryChain",
          label: "集成电路",
          subtitle: null,
          data: {},
        },
        ...Array.from({ length: 6 }, (_, i) => ({
          id: `node_${i}`,
          type: "IndustryNode",
          label: `环节${i + 1}`,
          subtitle: null,
          data: {},
        })),
      ],
      "",
    );
    response.graph.edges = Array.from({ length: 6 }, (_, i) => ({
      source: "chain_1",
      target: `node_${i}`,
      label: "HAS_NODE",
      data: {},
    }));
    return response;
  }

  it("全量统计每个实体的真实关系，超过 5 条不截断且不带总数前缀", () => {
    const summaries = panoramaNodeRelationSummaries(relationResponse());

    const center = summaries.get("chain_1");
    expect(center).toBeDefined();
    // 不带「共 N 条：」统计前缀，直接列关系线。
    expect(center).not.toContain("共 ");
    // 6 条关系全部列出（旧逻辑只显示前 5 条）。
    for (let i = 1; i <= 6; i++) {
      expect(center).toContain(`环节${i}`);
    }
    expect(summaries.get("node_0")).toBe("HAS_NODE ← 集成电路");
  });

  it("关系类型经展示函数中文化，对端实体不在子图时回退 id", () => {
    const response = relationResponse();
    response.graph.edges = [
      { source: "node_0", target: "unknown_vid", label: "COVERS_CHAIN", data: {} },
    ];
    const summaries = panoramaNodeRelationSummaries(response, {
      edgeLabelDisplay: () => "链上资讯关系",
    });

    expect(summaries.get("node_0")).toBe("链上资讯关系 → unknown_vid");
  });

  it("没有真实边的实体不进入统计结果", () => {
    const response = relationResponse();
    response.graph.edges = [];
    const summaries = panoramaNodeRelationSummaries(response);

    expect(summaries.size).toBe(0);
  });

  it("传入 edges 时仅统计指定边集合（画布口径，与画布渲染数量一致）", () => {
    const response = relationResponse();
    // 子图全量有 6 条边，画布口径只渲染其中 2 条。
    const summaries = panoramaNodeRelationSummaries(response, {
      edges: [
        { source: "chain_1", target: "node_0", label: "HAS_NODE", data: {} },
        { source: "chain_1", target: "node_1", label: "HAS_NODE", data: {} },
      ],
    });

    // 只统计传入的 2 条边，且不带总数前缀。
    expect(summaries.get("chain_1")).toBe(
      "HAS_NODE → 环节1；HAS_NODE → 环节2",
    );
    expect(summaries.has("node_0")).toBe(true);
    expect(summaries.has("node_2")).toBe(false);
  });

  it("传入 labelById 时优先用它解析端点名（画布虚拟中心等展示元素）", () => {
    const response = relationResponse();
    // 分层展示连线：虚拟中心不在全量实体并集里，靠 labelById 显示产业名。
    const summaries = panoramaNodeRelationSummaries(response, {
      edges: [
        {
          source: "__panorama_center__",
          target: "node_0",
          label: "关键技术",
          data: {},
        },
      ],
      labelById: new Map([["__panorama_center__", "集成电路"]]),
    });

    expect(summaries.get("node_0")).toBe("关键技术 ← 集成电路");
    // node_0 不在 labelById 里，回退全量并集标签「环节1」。
    expect(summaries.get("__panorama_center__")).toBe("关键技术 → 环节1");
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

  it("图库未写置信度时按边类型规则推导具体数值", () => {
    // 任职类：结构化源表，确定性较高。
    expect(
      panoramaEdgeConfidence({
        source: "person_1",
        target: "org_1",
        label: "AFFILIATED_WITH",
        data: {},
      }),
    ).toBeCloseTo(0.85);
    // 产业链结构边：随链定义入图，必然成立。
    expect(
      panoramaEdgeConfidence({
        source: "chain_1",
        target: "node_1",
        label: "HAS_NODE",
        data: {},
      }),
    ).toBeCloseTo(0.9);
    // 兜底表未覆盖的边类型：统一默认值。
    expect(
      panoramaEdgeConfidence({
        source: "a",
        target: "b",
        label: "SOME_NEW_TYPE",
        data: {},
      }),
    ).toBeCloseTo(0.8);
  });
});

describe("panoramaProvenanceCards", () => {
  function provenanceResponse(): IndustryChainPanoramaQueryResponse {
    const response = responseWithNodes(
      [
        {
          id: "chain_IC0007",
          type: "IndustryChain",
          label: "集成电路",
          subtitle: null,
          sourceTable: "dwd_industry_chain",
          sourceField: "chain_name",
          data: {},
        },
        {
          id: "org_1",
          type: "Organization",
          label: "华南智能芯片",
          subtitle: null,
          sourceTable: "dwd_organization",
          sourceField: "org_name",
          data: {},
        },
      ],
      "",
    );
    response.layers = [
      {
        key: "leading_expert",
        title: "领军专家",
        total: 1,
        items: [
          {
            id: "person_1",
            label: "张明远",
            type: "expert",
            subtitle: null,
            metric: null,
            metricValue: null,
            sourceTable: "dwd_scholar",
            sourceField: "scholar_name",
          },
        ],
      },
    ];
    response.graph.edges = [
      {
        source: "person_1",
        target: "org_1",
        label: "AFFILIATED_WITH",
        data: {},
      },
    ];
    return response;
  }

  it("未选中时展示全部实体卡与关系卡，格式与同事关系页一致", () => {
    const cards = panoramaProvenanceCards(provenanceResponse());

    expect(cards.map((card) => card.id)).toEqual([
      "node:chain_IC0007",
      "node:org_1",
      "node:person_1",
      "edge:0:person_1:org_1",
    ]);
    const expertCard = cards[2];
    expect(expertCard.title).toBe("张明远 · 实体来源");
    expect(expertCard.sections[0].rows).toEqual([
      ["源数据表", "dwd_scholar"],
      ["英文字段名", "scholar_name"],
      ["图空间 VID", "person_1"],
    ]);
    const edgeCard = cards[3];
    expect(edgeCard.title).toContain("张明远 → 华南智能芯片");
    expect(edgeCard.sections.map((section) => section.title)).toEqual([
      "源实体：张明远",
      "目标实体：华南智能芯片",
    ]);
  });

  it("选中节点时只展示该实体卡", () => {
    const cards = panoramaProvenanceCards(provenanceResponse(), {
      selectedNodeId: "org_1",
    });

    expect(cards).toHaveLength(1);
    expect(cards[0].id).toBe("node:org_1");
    expect(cards[0].sections[0].rows).toEqual([
      ["源数据表", "dwd_organization"],
      ["英文字段名", "org_name"],
      ["图空间 VID", "org_1"],
    ]);
  });

  it("选中边时只展示 source/target/label 均匹配的关系卡", () => {
    const cards = panoramaProvenanceCards(provenanceResponse(), {
      selectedEdge: {
        source: "person_1",
        target: "org_1",
        label: "AFFILIATED_WITH",
      },
      edgeLabelDisplay: () => "任职",
    });

    expect(cards).toHaveLength(1);
    expect(cards[0].title).toBe("张明远 → 华南智能芯片 · 任职");
  });

  it("选中虚拟节点（画布展示元素）时返回空列表", () => {
    const cards = panoramaProvenanceCards(provenanceResponse(), {
      selectedNodeId: "__panorama_center__",
    });

    expect(cards).toEqual([]);
  });

  it("传入画布口径时仅展示可见实体卡与指定真实边的关系卡", () => {
    const response = provenanceResponse();
    response.graph.edges.push({
      source: "person_1",
      target: "chain_IC0007",
      label: "COVERS_CHAIN",
      data: {},
    });
    // 画布只渲染 org_1 / person_1 两个节点与一条真实边。
    const cards = panoramaProvenanceCards(response, {
      visibleNodeIds: new Set(["org_1", "person_1"]),
      edges: [
        {
          source: "person_1",
          target: "org_1",
          label: "AFFILIATED_WITH",
          data: {},
        },
      ],
    });

    expect(cards.map((card) => card.id)).toEqual([
      "node:org_1",
      "node:person_1",
      "edge:0:person_1:org_1",
    ]);
  });

  it("画布口径下选中边只在指定真实边范围内匹配关系卡", () => {
    const response = provenanceResponse();
    // 选中边存在于子图全量边中，但不在画布渲染的边集合里。
    const cards = panoramaProvenanceCards(response, {
      selectedEdge: {
        source: "person_1",
        target: "org_1",
        label: "AFFILIATED_WITH",
      },
      edges: [],
    });

    expect(cards).toEqual([]);
  });

  it("点击连到虚拟中心的分层连线：标题显示产业名，合成端点记录派生来源", () => {
    const response = provenanceResponse();
    // 子图没有 IndustryChain 节点时画布中心是页面合成的 __panorama_center__。
    const cards = panoramaProvenanceCards(response, {
      selectedEdge: {
        source: "__panorama_center__",
        target: "person_1",
        label: "汇聚核心专家",
      },
      visibleNodeIds: new Set(["__panorama_center__", "person_1"]),
      edges: [],
      matchEdges: [
        {
          source: "__panorama_center__",
          target: "person_1",
          label: "汇聚核心专家",
          data: { inferred: true },
        },
      ],
      labelById: new Map([
        ["__panorama_center__", "集成电路"],
        ["person_1", "张明远"],
      ]),
    });

    expect(cards).toHaveLength(1);
    // 标题与区段名显示画布标签（产业名），而不是内部合成 id。
    expect(cards[0].title).toContain("集成电路 → 张明远");
    expect(cards[0].sections[0].title).toBe("源实体：集成电路");
    // 合成展示元素按「查到即记」派生口径记录来源，不再全部显示「—」。
    expect(cards[0].sections[0].rows).toEqual([
      ["源数据表", "页面合成 · 查询入参"],
      ["英文字段名", "industry"],
      ["图空间 VID", "—"],
    ]);
  });

  it("点击分层展示连线（matchEdges 含 inferred 标记）出关系卡", () => {
    const response = provenanceResponse();
    // 画布分层展示连线：虚拟中心 → 分层实体，不在子图真实边里。
    // edges 只含真实边（未选中时展示的卡），matchEdges 含全部画布连线。
    const cards = panoramaProvenanceCards(response, {
      selectedEdge: {
        source: "chain_IC0007",
        target: "person_1",
        label: "汇聚核心专家",
      },
      visibleNodeIds: new Set(["chain_IC0007", "person_1"]),
      edges: [],
      matchEdges: [
        {
          source: "chain_IC0007",
          target: "person_1",
          label: "汇聚核心专家",
          data: { inferred: true },
        },
      ],
    });

    expect(cards).toHaveLength(1);
    expect(cards[0].title).toContain("集成电路 → 张明远");
    // 两端实体的溯源三要素照常展示，不再附带连线说明区段。
    expect(cards[0].sections.map((section) => section.title)).toEqual([
      "源实体：集成电路",
      "目标实体：张明远",
    ]);
  });

  it("实体缺少溯源字段时三要素行显示占位符", () => {
    const response = provenanceResponse();
    response.graph.nodes = [
      {
        id: "node_x",
        type: "IndustryNode",
        label: "未知来源节点",
        subtitle: null,
        data: {},
      },
    ];
    response.layers = [];
    response.graph.edges = [];

    const cards = panoramaProvenanceCards(response);

    expect(cards[0].sections[0].rows).toEqual([
      ["源数据表", "—"],
      ["英文字段名", "—"],
      ["图空间 VID", "node_x"],
    ]);
  });
});
