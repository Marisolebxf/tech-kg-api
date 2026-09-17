import { apiBase } from '../config'

export interface JobChangeEvent {
  /** 发生变化的控制面记录（"job:<id>" / "exec:<id>"），仅作"有变化"信号 */
  changed: string[]
  removed: string[]
}

/**
 * 订阅任务/执行变更 SSE：后端监视控制面表（Schedule 到点起跑、执行翻终态、
 * 暂停/恢复、增删），变更即时推送 jobs-changed 事件，前端无需定时轮询。
 * EventSource 断线自动重连；onOpen 在连接建立与每次重连成功时回调——重连
 * 期间可能漏事件，调用方应趁机全量重拉一次。返回关闭函数。
 */
export function subscribeJobEvents(
  onChange: (event: JobChangeEvent) => void,
  onOpen?: () => void,
): () => void {
  const source = new EventSource(`${apiBase}/v1/workflow-system/jobs/events`)
  source.addEventListener('open', () => onOpen?.())
  source.addEventListener('jobs-changed', (event) => {
    try {
      onChange(JSON.parse((event as MessageEvent<string>).data) as JobChangeEvent)
    } catch {
      onChange({ changed: [], removed: [] }) // 解析失败也当"有变化"触发一次重拉
    }
  })
  return () => source.close()
}
