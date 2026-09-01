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
    timeColumn: row.timeColumn || 'update_time',
  }
}

export function isSourceBindingComplete(row: SourceBindingRow): boolean {
  return Boolean(row.datasourceId && row.databaseName && row.tableName)
}
