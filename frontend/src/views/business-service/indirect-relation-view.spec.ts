import { describe, expect, it } from "vitest";

import type {
  ExpertIndirectRelationResult,
  IndirectNode,
} from "../../api/expertIndirectRelation";
import {
  buildIndirectRelationGraph,
  indirectSummaryRows,
  parseRelationTypes,
} from "./indirect-relation-view";

const core: IndirectNode = {
  id: "expert-1",
  name: "核心专家",
  entityType: "专家",
  labels: ["Person"],
  properties: { source_record_id: "P-1", organization_base: "dwd_scholar" },
};
const organization: IndirectNode = {
  id: "org-1",
  name: "测试机构",
  entityType: "机构",
  labels: ["Organization"],
  properties: { organization_id: "ORG-1", source_table: "organization" },
};
const paper: IndirectNode = {
  id: "paper-1",
  name: "测试论文",
  entityType: "论文",
  labels: ["Paper"],
  properties: { source_record_id: "DOC-1", metadata: { indexed: true } },
};

const result: ExpertIndirectRelationResult = {
  coreNode: core,
  pathDepth: 2,
  defaultPathDepth: 2,
  minStrength: 0.5,
  directNodeCount: 1,
  indirectNodeCount: 1,
  pathCount: 1,
  relationTypeCount: { 论文合作: 1 },
  averageStrength: 0.8,
  maxStrength: 0.8,
  directNodes: [organization],
  indirectNodes: [paper],
  paths: [
    {
      pathId: "path-1",
      depth: 2,
      relationType: "间接关系",
      strength: 0.8,
      pathText: "核心专家 → 测试机构 → 测试论文",
      targetNode: paper,
      nodes: [core, organization, paper],
      edges: [
        {
          id: "e-1",
          type: "AFFILIATED_WITH",
          source: core.id,
          target: organization.id,
          properties: { confidence: 0.9, match_method: "exact" },
        },
        {
          id: "e-2",
          type: "PUBLISHED_IN",
          source: paper.id,
          target: organization.id,
          properties: {},
        },
        {
          id: "e-2-copy",
          type: "PUBLISHED_IN",
          source: paper.id,
          target: organization.id,
          properties: {},
        },
      ],
    },
  ],
};

describe("indirect relation view model", () => {
  it("normalizes relation filters", () => {
    expect(parseRelationTypes("论文合作、校友; 企业关联")).toEqual([
      "论文合作",
      "校友",
      "企业关联",
    ]);
  });

  it("deduplicates edges and maps graph metadata", () => {
    const graph = buildIndirectRelationGraph(result);
    expect(graph.nodes).toHaveLength(3);
    expect(graph.edges).toHaveLength(2);
    expect(graph.nodes[0].nodeType).toBe("main");
    expect(graph.edges[0].confidence).toBe(0.9);
  });

  it("builds populated and empty summary rows", () => {
    expect(indirectSummaryRows(result)).toContainEqual(["路径数量", "1 条"]);
    const empty = {
      ...result,
      relationTypeCount: {},
      directNodes: [],
      indirectNodes: [],
      paths: [],
    };
    expect(indirectSummaryRows(empty)[4][1]).toContain("暂无");
  });
});

describe("科技单节点间接关系展示", () => {
  it("使用中文类型、来源证据和业务化节点关系", () => {
    const coreNode = {
      id: "person_a",
      name: "专家甲",
      entityType: "科技专家",
      labels: ["Person"],
      properties: { source_table: "dwd_scholar", source_record_id: "A" },
    };
    const researchOrg = {
      id: "org_b",
      name: "测试研究院",
      entityType: "科研机构",
      labels: ["organization_base", "Organization"],
      properties: { organization_base: "dwd_organization", source_record_id: "B" },
    };
    const orgResult: ExpertIndirectRelationResult = {
      coreNode: coreNode,
      pathDepth: 2,
      defaultPathDepth: 2,
      minStrength: 0.5,
      directNodeCount: 0,
      indirectNodeCount: 1,
      pathCount: 1,
      relationTypeCount: { 机构关联: 1 },
      averageStrength: 0.8,
      maxStrength: 0.8,
      directNodes: [],
      indirectNodes: [researchOrg],
      paths: [{
        pathId: "p1",
        depth: 1,
        relationType: "机构关联",
        strength: 0.8,
        pathText: "专家甲 -> 测试研究院",
        targetNode: researchOrg,
        nodes: [coreNode, researchOrg],
        edges: [{
          id: "e1",
          type: "HAS_KEYWORD",
          source: coreNode.id,
          target: researchOrg.id,
          properties: { confidence: 0.8 },
        }],
      }],
    };

    const graph = buildIndirectRelationGraph(orgResult);
    expect(graph.nodes[0].relations).toBe("核心节点");
    expect(graph.nodes[1].entityType).toBe("科研机构");
    expect(graph.nodes[1].relations).toBe("间接关联节点");
    expect(graph.nodes[1].evidence).toEqual([
      "来源表：dwd_organization",
      "源记录：B",
    ]);
    expect(graph.nodes[1].evidence).not.toContain(orgResult.paths[0].pathText);
    expect(graph.edges[0]).toMatchObject({
      label: "关键词关联",
      category: "机构关联",
      confidence: 0.8,
    });
  });
});
