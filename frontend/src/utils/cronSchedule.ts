/**
 * 周期任务调度：cron 生成与人话描述。
 * JobLaunchDialog（构建 + 预览）与 GraphBuildView（任务列表展示）共用，
 * 保证"配置时看到的"和"列表里显示的"是同一套语义。
 */

export type ScheduleFrequency = '每天' | '每12小时' | '每6小时' | '每周'

const WEEKDAY_LABELS: Record<number, string> = {
  0: '周日',
  1: '周一',
  2: '周二',
  3: '周三',
  4: '周四',
  5: '周五',
  6: '周六',
}

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

/**
 * 由「频率 + 首次执行时间（锚点）(+ 每周的星期)」生成 5 段 cron。
 * 锚点语义：所选时刻即第一次触发，之后按频率顺延——
 * 每12小时选 02:00 → `0 2,14 * * *`（02:00、14:00 各一次），
 * 不再出现"选了 02:00 实际跑 00:00/12:00"的错位。
 */
export function buildScheduleCron(frequency: ScheduleFrequency, time: string, weekday = 1): string {
  const [h, m] = time.split(':')
  const hour = Math.min(Math.max(Number(h) || 0, 0), 23)
  const min = Math.min(Math.max(Number(m) || 0, 0), 59)
  if (frequency === '每周') {
    return `${min} ${hour} * * ${weekday}`
  }
  const step = frequency === '每12小时' ? 12 : frequency === '每6小时' ? 6 : 0
  if (!step) {
    return `${min} ${hour} * * *`
  }
  const hours = Array.from({ length: 24 / step }, (_, i) => (hour + i * step) % 24).sort((a, b) => a - b)
  return `${min} ${hours.join(',')} * * *`
}

/** 把 5 段 cron 人话化；认不出的形状回退为 `cron <原文>`，保证任意旧任务仍可读。 */
export function describeCron(cron: string): string {
  const parts = String(cron || '').trim().split(/\s+/)
  if (parts.length !== 5) {
    return `cron ${cron}`
  }
  const [min, hour, dom, mon, dow] = parts
  if (dom !== '*' || mon !== '*' || !/^\d+$/.test(min)) {
    return `cron ${cron}`
  }
  const mm = pad(Number(min))

  if (dow !== '*') {
    // 只认"单一星期几"；范围/列表（如 1-5）保持原文，避免误译成"每天"
    if (!/^\d+$/.test(dow) || !/^\d+$/.test(hour)) {
      return `cron ${cron}`
    }
    const label = WEEKDAY_LABELS[Number(dow) % 7]
    return label ? `每${label} ${pad(Number(hour))}:${mm}` : `cron ${cron}`
  }

  const times = (hours: number[]) => hours.map((h) => `${pad(h)}:${mm}`).join('、')

  if (/^\d+$/.test(hour)) {
    return `每天 ${pad(Number(hour))}:${mm}`
  }

  if (hour.startsWith('*/')) {
    const step = Number(hour.slice(2))
    if (!Number.isInteger(step) || step <= 0 || 24 % step !== 0) {
      return `cron ${cron}`
    }
    const hours = Array.from({ length: 24 / step }, (_, i) => i * step)
    return `每${step}小时 · ${times(hours)}`
  }

  const rawHours = hour.split(',')
  if (rawHours.every((h) => /^\d+$/.test(h))) {
    const nums = [...new Set(rawHours.map(Number))].sort((a, b) => a - b)
    const step = nums.length > 1 ? nums[1] - nums[0] : 0
    const uniform = nums.length > 1 && nums.every((h, i) => i === 0 || h - nums[i - 1] === step)
    if (uniform && step === 12 && nums.length === 2) {
      return `每12小时 · ${times(nums)}`
    }
    if (uniform && step === 6 && nums.length === 4) {
      return `每6小时 · ${times(nums)}`
    }
    return `每天 ${times(nums)}`
  }

  return `cron ${cron}`
}
