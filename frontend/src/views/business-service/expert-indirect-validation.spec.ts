import { describe, expect, it } from "vitest";

import { validateExpertIndirectParameters } from "./expert-indirect-validation";

const validValues = {
  core_node_id: "4G7t0B0t",
  relation_types: "学术关联",
  path_depth: "2",
  min_strength: "0.65",
};

describe("科技单节点间接关系参数校验", () => {
  it.each([
    [
      "空 core_node_id",
      { core_node_id: "" },
      "core_node_id",
      "请输入核心专家或人才节点 ID",
    ],
    [
      "超过 64 字符的 core_node_id",
      { core_node_id: "A".repeat(65) },
      "core_node_id",
      "输入长度不能超过 64 个字符",
    ],
    [
      "core_node_id 包含异常字符",
      { core_node_id: "!#@!@#" },
      "core_node_id",
      "不能包含空格或 !@#￥%& 等异常字符",
    ],
    [
      "core_node_id 包含空格",
      { core_node_id: "person 123" },
      "core_node_id",
      "不能包含空格或 !@#￥%& 等异常字符",
    ],
    [
      "未选择 relation_types",
      { relation_types: "" },
      "relation_types",
      "请选择间接关系类型",
    ],
    [
      "path_depth=0",
      { path_depth: "0" },
      "path_depth",
      "路径分析深度只能填写 2 或 3",
    ],
    [
      "path_depth=1",
      { path_depth: "1" },
      "path_depth",
      "路径分析深度只能填写 2 或 3",
    ],
    [
      "path_depth=4",
      { path_depth: "4" },
      "path_depth",
      "路径分析深度只能填写 2 或 3",
    ],
    [
      "path_depth=5",
      { path_depth: "5" },
      "path_depth",
      "路径分析深度只能填写 2 或 3",
    ],
    [
      "65 位 path_depth",
      { path_depth: "9".repeat(65) },
      "path_depth",
      "路径分析深度只能填写 2 或 3",
    ],
    [
      "非数字 path_depth",
      { path_depth: "abc!@#" },
      "path_depth",
      "路径分析深度只能填写 2 或 3",
    ],
    [
      "min_strength=-0.1",
      { min_strength: "-0.1" },
      "min_strength",
      "最小关联强度必须在 0-1 范围内",
    ],
    [
      "min_strength=1.1",
      { min_strength: "1.1" },
      "min_strength",
      "最小关联强度必须在 0-1 范围内",
    ],
    [
      "65 位 min_strength",
      { min_strength: "9".repeat(65) },
      "min_strength",
      "最小关联强度必须在 0-1 范围内",
    ],
    [
      "非数字 min_strength",
      { min_strength: "abc!@#" },
      "min_strength",
      "最小关联强度必须在 0-1 范围内",
    ],
  ])("拒绝%s", (_name, overrides, field, message) => {
    const result = validateExpertIndirectParameters({
      ...validValues,
      ...overrides,
    });

    expect(result.payload).toBeNull();
    expect(result.errors[field]).toBe(message);
  });

  it("为可选参数应用默认值", () => {
    const result = validateExpertIndirectParameters({
      core_node_id: "4G7t0B0t",
      relation_types: "学术关联",
    });

    expect(result.payload).toEqual({
      core_node_id: "4G7t0B0t",
      relation_types: ["学术关联"],
      path_depth: 2,
      min_strength: 0.65,
    });
  });
});
