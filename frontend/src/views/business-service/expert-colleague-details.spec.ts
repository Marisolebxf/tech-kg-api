import { describe, expect, it } from 'vitest';
import { colleagueEntityRows, colleagueProvenanceCards } from './expert-colleague-details';

const nodes = [
  { id: 'a', type: 'expert', label: '赵刚', data: { title: '研究员', provenance: { sourceTable: 'dwd_scholar', sourceField: 'scholar_id', sourceValue: '0209a7v6' } } },
  { id: 'b', type: 'expert', label: '朱保君', data: { title: '副研究员' } },
  { id: 'org', type: 'organization', label: '共同机构' },
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
  it('选择赵刚读取该实体来源，不依赖顶层 evidence', () => {
    const cards = colleagueProvenanceCards(nodes, edges, 'a');
    expect(cards).toHaveLength(1);
    expect(cards[0]?.rows).toContainEqual(['源记录 ID', '0209a7v6']);
  });
  it('选择关系展示判定证据及两端实体，不夹带机构来源', () => {
    const cards = colleagueProvenanceCards(nodes, edges, undefined, edges[0]);
    expect(cards).toHaveLength(3);
    expect(cards[0]?.evidence).toEqual(['共同任职机构']);
    expect(cards.some(card => card.id === 'org')).toBe(false);
  });
  it('来源缺失明确标注，不借用其他实体来源', () => {
    const cards = colleagueProvenanceCards(nodes, edges, 'b');
    expect(cards).toHaveLength(1);
    expect(cards[0]?.rows).toContainEqual(['源记录 ID', '未提供']);
    expect(colleagueProvenanceCards(nodes, edges, 'missing')).toEqual([]);
  });
});
