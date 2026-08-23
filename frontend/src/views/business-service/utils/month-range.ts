const MONTH_PATTERN = /^(\d{4})-(0[1-9]|1[0-2])$/

function parseMonth(value: string | undefined): { year: number; month: number } | undefined {
  if (!value) return undefined
  const match = MONTH_PATTERN.exec(value)
  if (!match) return undefined
  return { year: Number(match[1]), month: Number(match[2]) }
}

export function monthRangeToApiDates(
  startMonth: string | undefined,
  endMonth: string | undefined,
): { start?: string; end?: string } {
  const start = parseMonth(startMonth)
  const end = parseMonth(endMonth)
  const result: { start?: string; end?: string } = {}

  if (start) result.start = `${startMonth}-01`
  if (end) {
    const lastDay = new Date(Date.UTC(end.year, end.month, 0)).getUTCDate()
    result.end = `${endMonth}-${String(lastDay).padStart(2, '0')}`
  }

  return result
}
