import { describe, expect, it } from "vitest";

import {
  isValidYearMonth,
  paperCooperationTimeErrors,
} from "./expert-paper-cooperation-validation";

const CURRENT_MONTH = "2026-09";

describe("科技专家论文合作关系时间校验", () => {
  it("要求开始月份和结束月份同时填写", () => {
    expect(paperCooperationTimeErrors("2024-01", undefined, CURRENT_MONTH)).toEqual({
      endTime: "开始时间和结束时间必须同时填写",
    });
    expect(paperCooperationTimeErrors(undefined, "2024-02", CURRENT_MONTH)).toEqual({
      startTime: "开始时间和结束时间必须同时填写",
    });
  });

  it("同时标记开始月份晚于结束月份", () => {
    expect(
      paperCooperationTimeErrors("2021-09", "2021-08", CURRENT_MONTH),
    ).toEqual({
      startTime: "开始时间不能晚于结束时间",
      endTime: "结束时间不能早于开始时间",
    });
  });

  it.each([
    ["startTime", "2027-01", "2027-01", "开始时间不能晚于当前月份"],
    ["endTime", "2026-10", "2026-10", "结束时间不能晚于当前月份"],
  ])("标记未来月份 %s", (field, month, pairedMonth, message) => {
    const startTime = field === "startTime" ? month : pairedMonth;
    const endTime = field === "endTime" ? month : pairedMonth;
    const errors = paperCooperationTimeErrors(startTime, endTime, CURRENT_MONTH);
    expect(errors[field]).toBe(message);
  });

  it("允许当前月份和两个空值", () => {
    expect(
      paperCooperationTimeErrors(CURRENT_MONTH, CURRENT_MONTH, CURRENT_MONTH),
    ).toEqual({});
    expect(paperCooperationTimeErrors(undefined, undefined, CURRENT_MONTH)).toEqual({});
  });

  it.each(["2021-8", "2021/08", "2021-13"])(
    "拒绝非法月份 %s",
    (value) => {
      expect(isValidYearMonth(value)).toBe(false);
      expect(paperCooperationTimeErrors(value, value, CURRENT_MONTH)).toEqual({
        startTime: "开始时间必须使用 YYYY-MM 格式",
        endTime: "结束时间必须使用 YYYY-MM 格式",
      });
    },
  );

  it.each(["2021-08", "2024-02", CURRENT_MONTH])("接受有效月份 %s", (value) => {
    expect(isValidYearMonth(value)).toBe(true);
  });
});
