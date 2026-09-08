// 退出或会话失效前发出的请求，其晚到响应不能恢复旧身份或清除新会话。
let sessionVersion = 0

export function currentSessionVersion(): number {
  return sessionVersion
}

export function invalidateSessionVersion(): void {
  sessionVersion += 1
}
