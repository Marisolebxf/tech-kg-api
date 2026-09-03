const YEAR_MONTH_PATTERN = /^(?:19|20)\d{2}-(?:0[1-9]|1[0-2])$/;

export function isValidYearMonth(value: string | undefined): value is string {
  return Boolean(value && YEAR_MONTH_PATTERN.test(value));
}

export function paperCooperationTimeErrors(
  startValue: string | undefined,
  endValue: string | undefined,
  currentMonth: string,
): Record<string, string> {
  const errors: Record<string, string> = {};
  const startTime = startValue?.trim() || undefined;
  const endTime = endValue?.trim() || undefined;

  if (Boolean(startTime) !== Boolean(endTime)) {
    if (!startTime) errors.startTime = "开始时间和结束时间必须同时填写";
    if (!endTime) errors.endTime = "开始时间和结束时间必须同时填写";
    return errors;
  }

  if (startTime && !isValidYearMonth(startTime)) {
    errors.startTime = "开始时间必须使用 YYYY-MM 格式";
  }
  if (endTime && !isValidYearMonth(endTime)) {
    errors.endTime = "结束时间必须使用 YYYY-MM 格式";
  }
  if (Object.keys(errors).length) return errors;

  if (startTime && endTime && startTime > endTime) {
    errors.startTime = "开始时间不能晚于结束时间";
    errors.endTime = "结束时间不能早于开始时间";
  }
  if (startTime && startTime > currentMonth) {
    errors.startTime = "开始时间不能晚于当前月份";
  }
  if (endTime && endTime > currentMonth) {
    errors.endTime = "结束时间不能晚于当前月份";
  }
  return errors;
}
