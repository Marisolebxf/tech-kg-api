/** 当前全局图空间：从 graphSpace store 读取；store 未就绪时回退本地缓存/构建默认。 */

import { graphSpace as configuredDefault } from '../config'
import { GRAPH_SPACE_STORAGE_KEY, useGraphSpaceStore } from '../stores/graphSpace'

export function currentGraphSpace(): string {
  try {
    const value = useGraphSpaceStore().current
    if (value) return value
  } catch {
    // pinia 未初始化（如单元测试），走回退
  }
  try {
    return localStorage.getItem(GRAPH_SPACE_STORAGE_KEY) || configuredDefault || 'dev'
  } catch {
    return configuredDefault || 'dev'
  }
}
