/** 当前登录用户 ID：从 auth store 读取；未登录或 store 未就绪时回退到本地缓存值。 */

import { useAuthStore } from '../stores/auth'

export function currentUserId(): string {
  try {
    const store = useAuthStore()
    const id = store.profile?.user?.id
    if (id !== undefined && id !== null && String(id) !== '') {
      return String(id)
    }
  } catch {
    // pinia 未初始化（如单元测试），走回退
  }
  return localStorage.getItem('tech-kg-schema-user-id') || 'platform-admin'
}

export function currentUserIsAdmin(): boolean {
  try {
    return Boolean(useAuthStore().profile?.isAdmin)
  } catch {
    return false
  }
}
