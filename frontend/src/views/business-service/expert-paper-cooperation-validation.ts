const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

export function isValidIsoDate(value: string | undefined): value is string {
  if (!value || !ISO_DATE_PATTERN.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return (
    parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day
  );
}

export function paperCooperationTimeErrors(
  startValue: string | undefined,
  endValue: string | undefined,
  today: string,
): Record<string, string> {
  const errors: Record<string, string> = {};
  const startTime = startValue?.trim() || undefined;
  const endTime = endValue?.trim() || undefined;
  const validStartTime = isValidIsoDate(startTime) ? startTime : undefined;
  const validEndTime = isValidIsoDate(endTime) ? endTime : undefined;

  // 非法格式和不存在的日历日期交给后端最终校验并返回统一接口错误。
  if (validStartTime && validEndTime && validStartTime > validEndTime) {
    errors.startTime = "开始时间不能晚于结束时间";
    errors.endTime = "结束时间不能早于开始时间";
  }
  if (validStartTime && validStartTime > today) {
    errors.startTime = "开始时间超出当前时间";
  }
  if (validEndTime && validEndTime > today) {
    errors.endTime = "结束时间超出当前时间";
  }
  return errors;
}
