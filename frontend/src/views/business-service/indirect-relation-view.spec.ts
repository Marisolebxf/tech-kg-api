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
