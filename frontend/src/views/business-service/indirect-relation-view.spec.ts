import { describe, expect, it } from "vitest";

import type { ExpertIndirectRelationResult } from "../../api/expertIndirectRelation";
import { buildIndirectRelationGraph } from "./indirect-relation-view";

describe("科技单节点间接关系展示", () => {
  it("使用中文类型、来源证据和业务化节点关系", () => {
    const core = {
      id: "person_a",
      name: "专家甲",
      entityType: "科技专家",
      labels: ["Person"],
      properties: { source_table: "dwd_scholar", source_record_id: "A" },
    };
    const organization = {
      id: "org_b",
      name: "测试研究院",
      entityType: "科研机构",
      labels: ["organization_base", "Organization"],
      properties: { organization_base: "dwd_organization", source_record_id: "B" },
    };
    const result: ExpertIndirectRelationResult = {
      coreNode: core,
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
      indirectNodes: [organization],
      paths: [{
        pathId: "p1",
        depth: 1,
        relationType: "机构关联",
        strength: 0.8,
        pathText: "专家甲 -> 测试研究院",
        targetNode: organization,
        nodes: [core, organization],
        edges: [{
          id: "e1",
          type: "HAS_KEYWORD",
          source: core.id,
          target: organization.id,
          properties: { confidence: 0.8 },
        }],
      }],
    };

    const graph = buildIndirectRelationGraph(result);
    expect(graph.nodes[0].relations).toBe("核心节点");
    expect(graph.nodes[1].entityType).toBe("科研机构");
    expect(graph.nodes[1].relations).toBe("间接关联节点");
    expect(graph.nodes[1].evidence).toEqual([
      "来源表：dwd_organization",
      "源记录：B",
    ]);
    expect(graph.nodes[1].evidence).not.toContain(result.paths[0].pathText);
    expect(graph.edges[0]).toMatchObject({
      label: "关键词关联",
      category: "机构关联",
      confidence: 0.8,
    });
  });
});
