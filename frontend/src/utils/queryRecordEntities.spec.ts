import { describe, expect, it } from 'vitest'
import { collectQueryEntityReferences, queryEntityName } from './queryRecordEntities'

describe('query entity references', () => {
  it('recognizes actual VIDs and expression columns, including quotes, zero and DOI slashes', () => {
    expect(collectQueryEntityReferences({
      vid: '"paper_10.1111/jth.14768"', 'id(v)': 0, 'v.id': 'person-1', name: '张三', count: 42,
    }).map((entity) => entity.vid)).toEqual(['paper_10.1111/jth.14768', '0', 'person-1'])
  })

  it('reads vertices, relation endpoints and path nodes without treating relation or business IDs as vertices', () => {
    const vertex = { id: 'person-1', labels: ['Person'], properties: { name_zh: '张三', org_id: 'org-business-id' } }
    const references = collectQueryEntityReferences({
      vid: 'person-1', v: vertex,
      edge: { id: 'relation-1', type: 'AFFILIATED_WITH', sourceId: 'person-1', targetId: 'org-1', properties: {} },
      path: JSON.stringify({ nodes: [vertex, { id: 'paper-1', labels: ['Paper'], properties: { title_en: 'Research' } }] }),
    })
    expect(references.map((entity) => entity.vid)).toEqual(['person-1', 'org-1', 'paper-1'])
    expect(references[0]?.embeddedNode).toEqual(vertex)
  })

  it('does not invent entity references for schema descriptions, aggregations or names', () => {
    expect(collectQueryEntityReferences({ Field: 'id', Type: 'string', Null: 'YES', Default: '__EMPTY__' })).toEqual([])
    expect(collectQueryEntityReferences({ count: 123, name: '机构', paper_id: 'business-id', text: '{invalid' })).toEqual([])
  })

  it('uses available name/title fields, skips blanks and supports tag-qualified names', () => {
    expect(queryEntityName({ id: 'p1', labels: ['Paper'], properties: { title_zh: '', title_en: 'English title' } })).toBe('English title')
    expect(queryEntityName({ id: 'person-1', labels: ['Person'], properties: { 'Person.name_zh': '张三', name: 'Zhang' } })).toBe('张三')
    expect(queryEntityName({ id: 'p1', labels: ['Paper'], properties: {} })).toBeUndefined()
  })
})
