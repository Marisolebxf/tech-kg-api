import { computed, reactive, ref, watch } from 'vue'

import { fetchExpertDirectRelation } from '../../api/expert-direct-relation'

import type { DirectRelationQueryRequest, DirectRelationQueryResponse, DocField } from './expert-direct-types'

const ENDPOINT = '/api/v1/kg-construction/expert-direct-relations/query'
const MAX_QUERY_LIMIT = 100

const requestFields: DocField[] = [
  { name: 'dataSource', type: 'string', required: '否', description: '数据来源：固定为 all' },
  { name: 'expertAId', type: 'string', required: '否', description: '专家A scholar_id 或姓名关键词' },
  { name: 'expertBId', type: 'string', required: '否', description: '专家B scholar_id 或姓名关键词' },
  { name: 'institution', type: 'string', required: '否', description: '机构关键词过滤' },
  { name: 'startTime', type: 'string', required: '否', description: '开始日期，格式 YYYY-MM-DD' },
  { name: 'endTime', type: 'string', required: '否', description: '结束日期，格式 YYYY-MM-DD' },
  { name: 'limit', type: 'number', required: '否', description: `返回结果数量，超过 ${MAX_QUERY_LIMIT} 时按最大值返回` },
]

const responseFields: DocField[] = [
  { name: 'taskName', type: 'string', description: '任务名称' },
  { name: 'input', type: 'object', description: '本次查询入参回显' },
  { name: 'total', type: 'number', description: '结果总数' },
  { name: 'items', type: 'array', description: '直接关系结果列表' },
  { name: 'items[].expertA', type: 'object', description: '专家A信息' },
  { name: 'items[].expertB', type: 'object', description: '专家B信息' },
  { name: 'items[].detailRows', type: 'array', description: '右侧结构化详情行' },
  { name: 'graph', type: 'object', description: '图谱节点和边' },
  { name: 'source', type: 'object', description: '实际数据来源信息' },
  { name: 'apiResultExample', type: 'object', description: '接口示例回显' },
]

export function useExpertDirectRelation(enabled: () => boolean) {
  const form = reactive<DirectRelationQueryRequest>({
    dataSource: 'all',
    expertAId: '',
    expertBId: '',
    institution: '',
    startTime: '',
    endTime: '',
    limit: 4,
  })

  const loading = ref(false)
  const errorMessage = ref('')
  const response = ref<DirectRelationQueryResponse | null>(null)

  const execute = async () => {
    if (!enabled()) return
    loading.value = true
    errorMessage.value = ''
    try {
      form.dataSource = 'all'
      form.limit = Math.max(1, Math.min(Number(form.limit) || 10, MAX_QUERY_LIMIT))
      response.value = await fetchExpertDirectRelation({ ...form })
    } catch (error) {
      const message = error instanceof Error ? error.message : '请求失败'
      errorMessage.value = message
    } finally {
      loading.value = false
    }
  }

  const lastTestTime = computed(() => {
    const first = response.value?.items?.[0]?.lastUpdatedAt
    return first || '待执行'
  })

  const apiExampleText = computed(() =>
    JSON.stringify(response.value ?? {}, null, 2),
  )

  const codeSamples = computed(() => {
    const payload = JSON.stringify(form, null, 2)
    return {
      python:
        `import json\nimport requests\n\nurl = "http://127.0.0.1:9002${ENDPOINT}"\npayload = ${payload}\n\nresponse = requests.post(url, json=payload, timeout=30)\nresponse.raise_for_status()\nprint(json.dumps(response.json(), ensure_ascii=False, indent=2))`,
      node:
        `const url = "http://127.0.0.1:9002${ENDPOINT}";\nconst payload = ${payload};\n\nasync function main() {\n  const response = await fetch(url, {\n    method: "POST",\n    headers: { "Content-Type": "application/json" },\n    body: JSON.stringify(payload),\n  });\n  if (!response.ok) throw new Error(\`HTTP \${response.status}\`);\n  console.log(await response.json());\n}\n\nmain().catch(console.error);`,
      curl:
        `curl -X POST "http://127.0.0.1:9002${ENDPOINT}" \\\n  -H "Content-Type: application/json" \\\n  -d '${payload}'`,
    }
  })

  watch(
    () => enabled(),
    (value) => {
      if (value) {
        void execute()
      }
    },
    { immediate: true },
  )

  return {
    endpoint: ENDPOINT,
    form,
    loading,
    errorMessage,
    response,
    lastTestTime,
    apiExampleText,
    requestFields,
    responseFields,
    codeSamples,
    execute,
  }
}
