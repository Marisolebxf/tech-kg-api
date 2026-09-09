export function safeLoginTarget(value: unknown): string {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) return ''
  if (/[\\\u0000-\u001f\u007f]/.test(value) || /^\/login(?:[/?#]|$)/.test(value)) return ''
  return value
}
