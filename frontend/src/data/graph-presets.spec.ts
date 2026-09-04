import { describe, expect, it } from "vitest";

import {
  getEdgeProvenance,
  getNodeProvenance,
  type GraphEdgeData,
  type GraphNodeData,
} from "./graph-presets";

const node = (overrides: Partial<GraphNodeData> = {}): GraphNodeData => ({
  id: "expert-1",
  label: "测试专家",
  nodeType: "expert",
  x: 0,
  y: 0,
  entityType: "科技专家",
  relations: "1 条",
  evidence: [],
  ...overrides,
});

const edge = (overrides: Partial<GraphEdgeData> = {}): GraphEdgeData => ({
  id: "edge-1",
  from: "expert-1",
  to: "org-1",
  label: "任职",
  category: "直接关系",
  ...overrides,
});

describe("graph provenance", () => {
  it("prefers explicit source fields and handles built-in node identifiers", () => {
    expect(
      getNodeProvenance(node({ sourceField: "scholar_id", sourceValue: "42" }))
        .evidences[0].fieldIdentifier,
    ).toBe("scholar_id = 42");
    expect(
      getNodeProvenance(node({ sourceRecordId: "SRC-1" })).evidences[0]
        .fieldIdentifier,
    ).toBe("source_record_id = SRC-1");
    expect(
      getNodeProvenance(node({ id: "core", nodeType: "main" })).evidences[0]
        .fieldIdentifier,
    ).toContain("EXPERT-10286");
    expect(
      getNodeProvenance(node({ id: "org-1", nodeType: "org" })).evidences[0]
        .fieldIdentifier,
    ).toContain("ORG-10018");
    expect(
      getNodeProvenance(node({ id: "paper-9", nodeType: "paper" })).evidences[0]
        .fieldIdentifier,
    ).toContain("PAPER-9");
  });

  it("builds path, inferred and direct edge provenance", () => {
    const from = node({ id: "expert-1" });
    const to = node({
      id: "org-1",
      label: "测试机构",
      nodeType: "org",
      entityType: "科技机构",
    });
    const path = getEdgeProvenance(edge({ category: "间接关系" }), from, to);
    expect(path.evidences).toHaveLength(3);
    expect(path.task.mode).toBe("两跳路径 + 共现规则");

    const inferred = getEdgeProvenance(
      edge({ category: "同事", inferred: true }),
      from,
      to,
    );
    expect(inferred.evidences).toHaveLength(2);
    expect(inferred.task.mode).toBe("任职时间交集 + 机构/部门匹配");

    const direct = getEdgeProvenance(edge({ matchMethod: "精确匹配" }));
    expect(direct.evidences).toHaveLength(1);
    expect(direct.task.mode).toBe("精确匹配");
  });
});
