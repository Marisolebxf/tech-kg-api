export function formatNow() {
  const now = new Date()
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
}

export function buildCodeExamples(apiPath: string, method: 'GET' | 'POST', payload: Record<string, unknown>) {
  const payloadJson = JSON.stringify(payload, null, 2)
  const origin = typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:8000'
  const url = `${origin}${apiPath}`

  const python =
    method === 'POST'
      ? `import json\nimport requests\n\nurl = "${url}"\npayload = ${payloadJson.replace(/"/g, '"')}\nresponse = requests.post(url, json=payload, timeout=30)\nresponse.raise_for_status()\nprint(json.dumps(response.json(), ensure_ascii=False, indent=2))`
      : `import requests\n\nurl = "${url}"\nresponse = requests.get(url, timeout=30)\nresponse.raise_for_status()\nprint(response.json())`

  const node =
    method === 'POST'
      ? `const url = "${url}";\nconst payload = ${payloadJson};\nconst response = await fetch(url, {\n  method: "POST",\n  headers: { "Content-Type": "application/json" },\n  body: JSON.stringify(payload),\n});\nif (!response.ok) throw new Error(\`HTTP \${response.status}\`);\nconsole.log(await response.json());`
      : `const response = await fetch("${url}");\nif (!response.ok) throw new Error(\`HTTP \${response.status}\`);\nconsole.log(await response.json());`

  const curl =
    method === 'POST'
      ? `curl --location "${url}" \\\n  --header "Content-Type: application/json" \\\n  --data '${JSON.stringify(payload)}'`
      : `curl --location "${url}"`

  return { python, node, curl }
}
