function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function wrap(className: string, text: string): string {
  return `<span class="${className}">${text}</span>`
}

/** Highlight JSON text: keys/properties vs values use different colors. */
export function highlightJson(source: string): string {
  const escaped = escapeHtml(source)
  return escaped
    .replace(/("(?:\\.|[^"\\])*")(\s*:)/g, (_, key, colon) => `${wrap('code-prop', key)}${colon}`)
    .replace(/(:\s*)("(?:\\.|[^"\\])*")/g, (_, colon, value) => `${colon}${wrap('code-value', value)}`)
    .replace(/(:\s*)(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g, (_, colon, value) => `${colon}${wrap('code-value', value)}`)
    .replace(/(:\s*)(true|false|null)/g, (_, colon, value) => `${colon}${wrap('code-value', value)}`)
}

/** Highlight a single code line (Python / Node / cURL / JSON fragment). */
export function highlightCodeLine(line: string): string {
  if (!line.trim()) {
    return ' '
  }

  let html = escapeHtml(line)

  html = html.replace(/("(?:\\.|[^"\\])*")(\s*:)/g, (_, key, colon) => `${wrap('code-prop', key)}${colon}`)
  html = html.replace(/(:\s*)("(?:\\.|[^"\\])*")/g, (_, colon, value) => `${colon}${wrap('code-value', value)}`)
  html = html.replace(/(:\s*)(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g, (_, colon, value) => `${colon}${wrap('code-value', value)}`)
  html = html.replace(/(:\s*)(true|false|null)/g, (_, colon, value) => `${colon}${wrap('code-value', value)}`)

  html = html.replace(/(^|\s)([A-Za-z_][\w]*)(\s*=)/g, (_, prefix, name, eq) => `${prefix}${wrap('code-prop', name)}${eq}`)
  html = html.replace(/(=\s*)("(?:\\.|[^"\\])*")/g, (_, eq, value) => `${eq}${wrap('code-value', value)}`)
  html = html.replace(/(=\s*)(-?\d+(?:\.\d+)?)/g, (_, eq, value) => `${eq}${wrap('code-value', value)}`)
  html = html.replace(/(=\s*)(\{|\[)/g, (_, eq, value) => `${eq}${wrap('code-value', value)}`)

  html = html.replace(/(--[\w-]+)(\s+)("(?:\\.|[^"\\])*")/g, (_, flag, space, value) => `${wrap('code-prop', flag)}${space}${wrap('code-value', value)}`)
  html = html.replace(/(--[\w-]+)(\s+)([^\s\\]+)/g, (_, flag, space, value) => `${wrap('code-prop', flag)}${space}${wrap('code-value', value)}`)

  return html
}

export function highlightJsonValue(value: unknown): string {
  return highlightJson(JSON.stringify(value, null, 2))
}
