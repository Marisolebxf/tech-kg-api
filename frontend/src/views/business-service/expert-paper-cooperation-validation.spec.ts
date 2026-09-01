import { describe, expect, it } from "vitest";

import {
  isValidIsoDate,
  paperCooperationTimeErrors,
} from "./expert-paper-cooperation-validation";

const TODAY = "2026-09-01";

describe("科技专家论文合作关系时间校验", () => {
  it("同时标记开始时间晚于结束时间", () => {
    expect(
      paperCooperationTimeErrors("2021-09-30", "2021-08-01", TODAY),
    ).toEqual({
      startTime: "开始时间不能晚于结束时间",
      endTime: "结束时间不能早于开始时间",
    });
  });

  it.each([
    ["startTime", "2027-01-01", undefined, "开始时间超出当前时间"],
    ["endTime", undefined, "2027-01-01", "结束时间超出当前时间"],
  ])("标记未来日期 %s", (field, startTime, endTime, message) => {
    expect(paperCooperationTimeErrors(startTime, endTime, TODAY)).toEqual({
      [field]: message,
    });
  });

  it("允许当天日期", () => {
    expect(paperCooperationTimeErrors(TODAY, TODAY, TODAY)).toEqual({});
  });

  it.each(["2021-08", "2021/08/01", "2021-02-30"])(
    "将非法日期 %s 交给后端最终校验",
    (value) => {
      expect(isValidIsoDate(value)).toBe(false);
      expect(paperCooperationTimeErrors(value, undefined, TODAY)).toEqual({});
      expect(paperCooperationTimeErrors(undefined, value, TODAY)).toEqual({});
    },
  );

  it.each(["2021-08-01", "2024-02-29", TODAY])("接受有效日期 %s", (value) => {
    expect(isValidIsoDate(value)).toBe(true);
  });
});
