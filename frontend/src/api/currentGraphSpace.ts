/** 当前全局图空间：已存在的 store 即使为空也不能回退到未经授权的默认值。
 * 仅无 Pinia 的独立调用使用构建默认值，不直接读跨账号 localStorage。 */

import { graphSpace as configuredDefault } from '../config'
import { useGraphSpaceStore } from '../stores/graphSpace'

export function currentGraphSpace(): string {
  try {
    return useGraphSpaceStore().current
  } catch {
    // pinia 未初始化（如单元测试），走回退
  }
  return configuredDefault || 'dev'
}
