import type { StructureItem } from '../../api/platformOverview'

/** 饼图几何（viewBox 160×160，中心 80,80，半径 64，12 点钟方向起顺时针）。 */
const CENTER = 80
const RADIUS = 64
/** 悬浮时沿扇形中角外移的视图单位数，形成「放大」互动感 */
const HOVER_OFFSET = 5
/** 占比 ≥5% 才在扇区内标百分比，窄段靠悬浮浮窗补充 */
const LABEL_MIN_PERCENT = 5

export interface PieSlice {
  item: StructureItem
  /** 扇形 path d（未含悬浮位移；100% 单段用整圆双弧特判） */
  path: string
  /** 百分比标签锚点（扇形质心方向 0.62r 处） */
  labelX: number
  labelY: number
  /** 悬浮外移向量（沿中角） */
  dx: number
  dy: number
  /** 窄段不标百分比（≤5%），避免文字溢出扇区 */
  showLabel: boolean
  percent: number
}

function point(angle: number, radius: number): [number, number] {
  return [CENTER + radius * Math.cos(angle), CENTER + radius * Math.sin(angle)]
}

const fmt = (value: number) => Math.round(value * 100) / 100

/** 构成图饼图分段由图例数据驱动：按 tone+ratio 逐段生成扇形 path 与标签锚点，
 *  与图例严格一致；ratio 缺额/为 0 的段不产生扇形，全空时由调用方落空态。 */
export function pieSlices(items: StructureItem[]): PieSlice[] {
  const valid = items.filter((item) => Number(item.ratio) > 0)
  const total = valid.reduce((sum, item) => sum + (Number(item.ratio) || 0), 0)
  if (total <= 0) return []
  let start = -Math.PI / 2
  const slices: PieSlice[] = []
  for (const item of valid) {
    const fraction = (Number(item.ratio) || 0) / total
    const end = start + fraction * Math.PI * 2
    const mid = (start + end) / 2
    let path: string
    if (fraction >= 0.999) {
      // 单段 100%：起点=终点的弧画不出图形，整圆拆成两条半圆弧
      const [ax, ay] = point(-Math.PI / 2, RADIUS)
      const [bx, by] = point(Math.PI / 2, RADIUS)
      path =
        `M ${fmt(ax)} ${fmt(ay)} A ${RADIUS} ${RADIUS} 0 1 1 ${fmt(bx)} ${fmt(by)} ` +
        `A ${RADIUS} ${RADIUS} 0 1 1 ${fmt(ax)} ${fmt(ay)} Z`
    } else {
      const [ax, ay] = point(start, RADIUS)
      const [bx, by] = point(end, RADIUS)
      const largeArc = end - start > Math.PI ? 1 : 0
      path = `M ${CENTER} ${CENTER} L ${fmt(ax)} ${fmt(ay)} A ${RADIUS} ${RADIUS} 0 ${largeArc} 1 ${fmt(bx)} ${fmt(by)} Z`
    }
    slices.push({
      item,
      path,
      labelX: fmt(CENTER + Math.cos(mid) * RADIUS * 0.62),
      labelY: fmt(CENTER + Math.sin(mid) * RADIUS * 0.62),
      dx: fmt(Math.cos(mid) * HOVER_OFFSET),
      dy: fmt(Math.sin(mid) * HOVER_OFFSET),
      showLabel: item.ratio >= LABEL_MIN_PERCENT,
      percent: item.ratio,
    })
    start = end
  }
  return slices
}
