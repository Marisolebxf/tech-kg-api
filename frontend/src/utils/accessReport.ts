import type { AccessEntry, AccessReport } from '../api/workflowOperations'

export interface AccessChip {
  group: string
  name: string
  read: boolean
  write: boolean
  detail: string
}

/** 把 access 报告拉平成 chips；跳过 `_` 开头的元信息键（_unparsed/_ngql）。 */
export function accessChips(report: AccessReport | null | undefined): AccessChip[] {
  if (!report) return []
  const chips: AccessChip[] = []

  for (const [db, tables] of Object.entries(report.mysql || {})) {
    if (db.startsWith('_')) continue
    for (const [table, entry] of Object.entries(tables || {})) {
      const ops = entry.ops || []
      chips.push({
        group: 'MySQL',
        name: db === '_' ? table : `${db}.${table}`,
        read: ops.some((op) => op === 'SELECT' || op === 'read'),
        write: ops.some((op) => op !== 'SELECT' && op !== 'read'),
        detail: `${entry.statements ?? 0} 次`,
      })
    }
  }

  for (const [kind, names] of Object.entries(report.graph || {})) {
    if (kind.startsWith('_')) continue
    for (const [name, entry] of Object.entries(names || {})) {
      const ops = entry.ops || []
      chips.push({
        group: kind === 'edge' ? 'Graph 边' : 'Graph 点',
        name,
        read: ops.includes('read'),
        write: ops.includes('write'),
        detail: `${entry.count ?? 0} 次`,
      })
    }
  }

  for (const [collection, entry] of Object.entries(report.milvus || {})) {
    const ops = entry.ops || []
    chips.push({
      group: 'Milvus',
      name: collection,
      read: ops.includes('read'),
      write: ops.includes('write'),
      detail: `${entry.count ?? 0} 次`,
    })
  }

  for (const [bucket, label] of [
    ['llm', 'LLM'],
    ['embedding', 'Embedding'],
  ] as const) {
    for (const [model, entry] of Object.entries(report[bucket] || {})) {
      const failures = entry.failures || 0
      chips.push({
        group: label,
        name: model,
        read: true,
        write: false,
        detail: `${entry.calls ?? 0} 调用${failures ? ` · ${failures} 失败` : ''}`,
      })
    }
  }

  return chips
}

function mergeEntries(list: AccessEntry[]): AccessEntry {
  const merged: AccessEntry = {}
  const ops = new Set<string>()
  for (const entry of list) {
    for (const op of entry.ops || []) ops.add(op)
    merged.count = (merged.count || 0) + (entry.count || 0)
    merged.statements = (merged.statements || 0) + (entry.statements || 0)
  }
  merged.ops = [...ops]
  return merged
}

/** execution 级聚合：合并各 step 的 access 报告（跨 step 计数累加、ops 并集去重）。 */
export function mergeAccessReports(
  reports: (AccessReport | null | undefined)[],
): AccessReport | undefined {
  const valid = reports.filter((item): item is AccessReport => !!item)
  if (!valid.length) return undefined
  const out: AccessReport = {}

  // mysql/graph 是两层（db→table / kind→name），milvus 是单层（collection）
  for (const key of ['mysql', 'graph'] as const) {
    const merged: Record<string, Record<string, AccessEntry>> = {}
    let has = false
    for (const report of valid) {
      const bucket = report[key]
      if (!bucket) continue
      has = true
      for (const [k1, sub] of Object.entries(bucket)) {
        const target = merged[k1] || (merged[k1] = {})
        for (const [k2, entry] of Object.entries(sub || {})) {
          target[k2] = mergeEntries([target[k2] || {}, entry])
        }
      }
    }
    if (has) out[key] = merged
  }

  {
    const merged: Record<string, AccessEntry> = {}
    let has = false
    for (const report of valid) {
      const bucket = report.milvus
      if (!bucket) continue
      has = true
      for (const [collection, entry] of Object.entries(bucket)) {
        merged[collection] = mergeEntries([merged[collection] || {}, entry])
      }
    }
    if (has) out.milvus = merged
  }

  for (const key of ['llm', 'embedding'] as const) {
    const merged: Record<string, AccessEntry> = {}
    let has = false
    for (const report of valid) {
      const bucket = report[key]
      if (!bucket) continue
      has = true
      for (const [model, entry] of Object.entries(bucket || {})) {
        const target = merged[model] || (merged[model] = {})
        target.calls = (target.calls || 0) + (entry.calls || 0)
        target.failures = (target.failures || 0) + (entry.failures || 0)
      }
    }
    if (has) out[key] = merged
  }

  return out
}
