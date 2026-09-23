/** 当前全局图空间：从 graphSpace store 读取；store 未就绪时回退构建默认。
 * 持久化已按用户隔离（store 内处理），这里不再直接读 localStorage——
 * 那会把别的账号（或旧版裸字符串）的选中值漏给当前用户。 */

import { graphSpace as configuredDefault } from '../config'
import { useGraphSpaceStore } from '../stores/graphSpace'

export function currentGraphSpace(): string {
  try {
    const value = useGraphSpaceStore().current
    if (value) return value
  } catch {
    // pinia 未初始化（如单元测试），走回退
  }
  return configuredDefault || 'dev'
}
