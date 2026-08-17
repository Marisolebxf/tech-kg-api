export type ApiResponse<T> = {
  code?: number
  success?: boolean
  data?: T
  msg?: string
  message?: string
  items?: T
  total?: number
}

export class BusinessError extends Error {
  code: number
  constructor(code: number, message: string) {
    super(message)
    this.name = 'BusinessError'
    this.code = code
  }
}

export const unwrapApiResponse = <T>(response: ApiResponse<T>): T => {
  if (response && typeof response === 'object') {
    const code = response.code ?? (response.success === false ? -1 : 0)
    if (code !== 0) {
      throw new BusinessError(code, response.msg ?? response.message ?? '业务异常')
    }
    if ('data' in response && response.data !== undefined) {
      return response.data as T
    }
    if ('items' in response && response.items !== undefined) {
      return response.items as T
    }
  }
  return response as unknown as T
}
