import { computed } from 'vue'
import { useGraphSpaceStore } from '../stores/graphSpace'

/** 页面允许查看；仅实际修改和任务控制使用此能力。服务端仍逐资源鉴权。 */
export function useSpacePermissions() {
  const spaces = useGraphSpaceStore()
  const canWrite = computed(() => spaces.canWrite())
  const canReview = computed(() => spaces.canReview())
  const readonlyReason = '当前图空间仅可查看，无操作权限'
  return { spaces, canWrite, canReview, readonlyReason }
}
