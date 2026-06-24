import type { ScaffoldDemoPayload } from '../../../../types/kg-module'
import { buildCodeExamples } from '../../../../composables/useDeveloperExamples'

import expertAlumniRelation from './expert-alumni-relation'
import expertColleagueRelation from './expert-colleague-relation'
import expertCooperationAchievement from './expert-cooperation-achievement'
import expertIndirectRelation from './expert-indirect-relation'
import industryChainPanorama from './industry-chain-panorama'
import industryChainTopnEvent from './industry-chain-topn-event'

const rawDemos: Record<string, ScaffoldDemoPayload> = {
  'expert-indirect-relation': expertIndirectRelation,
  'expert-cooperation-achievement': expertCooperationAchievement,
  'expert-colleague-relation': expertColleagueRelation,
  'expert-alumni-relation': expertAlumniRelation,
  'industry-chain-topn-event': industryChainTopnEvent,
  'industry-chain-panorama': industryChainPanorama,
}

function withCodeExamples(demo: ScaffoldDemoPayload): ScaffoldDemoPayload {
  const requestPayload =
    demo.httpMethod === 'POST'
      ? Object.fromEntries(demo.requestFields.map((field) => [field.name, `示例${field.name}`]))
      : {}
  const codeExamples = buildCodeExamples(demo.apiPath, demo.httpMethod, requestPayload)
  return { ...demo, codeExamples }
}

export function getScaffoldDemo(moduleCode: string): ScaffoldDemoPayload | undefined {
  const demo = rawDemos[moduleCode]
  if (!demo) return undefined
  return withCodeExamples(demo)
}

export function structuredResultToRows(structuredResult: Record<string, unknown>): (string | number)[][] {
  return Object.entries(structuredResult).map(([key, value]) => {
    if (value && typeof value === 'object' && 'displayText' in (value as Record<string, unknown>)) {
      return [key, (value as { displayText: string }).displayText]
    }
    if (Array.isArray(value)) return [key, value.join('、')]
    return [key, String(value ?? '-')]
  })
}
