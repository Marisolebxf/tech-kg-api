export interface SourceBindingRow {
  datasourceId: string
  databaseName: string
  tableName: string
  pkColumn: string
  timeColumn: string
}

export function emptySourceBindingRow(): SourceBindingRow {
  return {
    datasourceId: '',
    databaseName: '',
    tableName: '',
    pkColumn: 'id',
    timeColumn: 'update_time',
  }
}

export function toSourcePayload(row: SourceBindingRow): {
  datasourceId: string
  databaseName: string
  tableName: string
  pkColumn: string
  timeColumn: string
} | null {
  if (!row.datasourceId || !row.databaseName || !row.tableName) return null
  return {
    datasourceId: row.datasourceId,
    databaseName: row.databaseName,
    tableName: row.tableName,
    pkColumn: row.pkColumn || 'id',
    // 时间列按用户实际选择提交（可为空 = 无时间列，后端走 pk keyset 增量）；
    // 此前空值被强转为 'update_time'，表里没有该列的绑定到运行时才炸 SQL
    timeColumn: row.timeColumn,
  }
}

export function isSourceBindingComplete(row: SourceBindingRow): boolean {
  return Boolean(row.datasourceId && row.databaseName && row.tableName)
}
