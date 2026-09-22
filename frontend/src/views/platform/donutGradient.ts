import type { StructureItem } from '../../api/platformOverview'

/** 占比环形图由图例数据驱动：按 tone+ratio 累计生成 conic-gradient，与图例严格一致。
 *  ratio 为整数百分比（后端保证合计 100）；缺失/不足时剩余弧段留中性灰。 */
export function donutGradient(items: StructureItem[]): string {
  if (!items.length) return 'conic-gradient(#e5edf8 0 100%)'
  const stops: string[] = []
  let start = 0
  for (const item of items) {
    const end = Math.min(100, start + Math.max(0, Number(item.ratio) || 0))
    if (end > start) stops.push(`${item.tone} ${start}% ${end}%`)
    start = end
  }
  if (start < 100) stops.push(`#e5edf8 ${start}% 100%`)
  return `conic-gradient(${stops.join(',')})`
}
