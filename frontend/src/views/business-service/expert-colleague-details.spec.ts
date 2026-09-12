import { describe, expect, it } from 'vitest';
import { colleagueEntityRows, colleagueProvenanceCards } from './expert-colleague-details';

const nodes = [
  { id: 'a', type: 'expert', label: '赵刚', data: { title: '研究员', provenance: { sourceTable: 'dwd_scholar', sourceField: 'scholar_id', sourceValue: '0209a7v6' } } },
  { id: 'b', type: 'expert', label: '朱保君', data: { title: '副研究员', provenance: { sourceTable: 'dwd_scholar', sourceField: 'scholar_id' } } },
  { id: 'org', type: 'organization', label: '共同机构', data: { provenance: { sourceTable: 'dwd_org_stock_base', sourceField: 'organization_id' } } },
];
const edges = [{ source: 'a', target: 'b', label: '同事关系', data: { evidence: ['共同任职机构'], ruleName: '同事关系判定规则' } }];

describe('同事关系详情', () => {
  it('职称作为实体属性展示，选中与全量视图均不混入关系或关系置信度', () => {
    for (const selected of [undefined, 'a']) {
      const rows = colleagueEntityRows(nodes, selected);
      expect(rows).toContainEqual(['职称/职务', '研究员']);
      expect(rows.some(([label]) => /关系|置信度/.test(label))).toBe(false);
    }
    expect(colleagueEntityRows(nodes, 'org').some(([label]) => label === '职称/职务')).toBe(false);
  });
  it('展示所有实体和所有类型的关系，每个来源只有三项', () => {
    const allEdges = [...edges, { source: 'a', target: 'org', label: 'AFFILIATED_WITH' }, { source: 'b', target: 'org', label: 'AFFILIATED_WITH' }];
    const cards = colleagueProvenanceCards(nodes, allEdges);
    expect(cards).toHaveLength(6);
    for (const card of cards) {
      for (const section of card.sections) {
        expect(section.rows.map(([label]) => label)).toEqual(['源数据表', '英文字段名', '图空间 VID']);
      }
    }
    expect(cards[0]?.sections[0]?.rows).toEqual([
      ['源数据表', 'dwd_scholar'], ['英文字段名', 'scholar_id'], ['图空间 VID', 'a'],
    ]);
  });
  it('关系分别展示源实体和目标实体真实来源', () => {
    const cards = colleagueProvenanceCards(nodes, [{ source: 'a', target: 'org', label: 'AFFILIATED_WITH' }]);
    const relation = cards[3]!;
    expect(relation.sections.map(section => section.title)).toEqual(['源实体：赵刚', '目标实体：共同机构']);
    expect(relation.sections[0]?.rows).toEqual(cards[0]?.sections[0]?.rows);
    expect(relation.sections[1]?.rows).toEqual(cards[2]?.sections[0]?.rows);
  });
  it('真实字段优先，不借用其他实体来源', () => {
    const cards = colleagueProvenanceCards([
      { ...nodes[0]!, data: { details: { source_table: 'actual_table', source_field: 'actual_id' }, provenance: { sourceTable: '-', sourceField: '-' } } },
    ], []);
    expect(cards[0]?.sections[0]?.rows).toEqual([
      ['源数据表', 'actual_table'], ['英文字段名', 'actual_id'], ['图空间 VID', 'a'],
    ]);
    expect(colleagueProvenanceCards([], [])).toEqual([]);
  });
  it('选中实体仅展示该实体，选中边仅展示该边两端，清除选中恢复全图', () => {
    const relation = { source: 'a', target: 'org', label: 'AFFILIATED_WITH' };
    const allEdges = [...edges, relation];
    const selected = colleagueProvenanceCards(nodes, allEdges, 'a');
    expect(selected).toHaveLength(1);
    expect(selected[0]?.id).toBe('node:a');
    const selectedRelation = colleagueProvenanceCards(nodes, allEdges, undefined, relation);
    expect(selectedRelation).toHaveLength(1);
    expect(selectedRelation[0]?.sections.map(section => section.title)).toEqual(['源实体：赵刚', '目标实体：共同机构']);
    for (const section of selectedRelation[0]!.sections) {
      expect(section.rows).toHaveLength(3);
      expect(section.rows.every(([, value]) => value.trim() !== '')).toBe(true);
    }
    expect(colleagueProvenanceCards(nodes, allEdges)).toHaveLength(5);
    expect(colleagueProvenanceCards(nodes, allEdges, 'nonexistent')).toEqual([]);
  });
});
