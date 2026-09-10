import type { ColleagueGraphNode, ColleagueGraphEdge } from '../../api/expertColleagueRelation';

type Row = readonly [string, string];
const text = (value: unknown) => value == null || value === '' || value === '-' ? '未提供' : String(value);
const entityType = (node: ColleagueGraphNode) => node.type === 'expert' ? '科技专家' : node.type === 'organization' ? '共同机构' : '合作成果';

export function colleagueEntityRows(nodes: ColleagueGraphNode[], selectedId?: string): Row[] {
  const visible = selectedId ? nodes.filter(node => node.id === selectedId) : nodes;
  return visible.flatMap((node, index): Row[] => {
    const rows: Row[] = [
      [selectedId ? '实体名称' : `实体 ${index + 1}`, `${node.label}（${node.id}）`],
      ['类型', entityType(node)],
    ];
    if (node.type === 'expert') {
      rows.push(['职称/职务', text(node.data?.title)], ['所属机构', text(node.data?.organization)]);
      if (node.data?.department) rows.push(['部门', text(node.data.department)]);
    }
    return rows;
  });
}

export function colleagueProvenanceCards(
  nodes: ColleagueGraphNode[], edges: ColleagueGraphEdge[], selectedId?: string,
  selectedEdge?: Pick<ColleagueGraphEdge, 'source' | 'target' | 'label'>,
): Array<{ id: string; title: string; rows: Row[]; evidence: string[] }> {
  const visible = selectedId ? nodes.filter(node => node.id === selectedId) : selectedEdge
    ? nodes.filter(node => node.id === selectedEdge.source || node.id === selectedEdge.target) : nodes;
  const cards = visible.map(node => {
    const p = node.data?.provenance ?? {};
    return {
      id: node.id, title: `${node.label} · 实体来源`,
      rows: [
        ['图空间 VID', node.id],
        ['来源系统', text(node.data?.details?.source_system)],
        ['源数据表', text(p.sourceTable)],
        ['源字段', text(p.sourceField)],
        ['源记录 ID', text(p.sourceValue)],
        ['入图批次', text(p.ingestBatch)],
        ['入图时间', text(p.ingestTime)],
      ] as Row[],
      evidence: [] as string[],
    };
  });
  const relations = selectedId ? [] : selectedEdge
    ? edges.filter(edge => edge.source === selectedEdge.source && edge.target === selectedEdge.target && edge.label === selectedEdge.label)
    : edges.filter(edge => edge.label === '同事关系');
  for (const edge of relations) {
    const d = edge.data ?? {};
    const name = (id: string) => nodes.find(node => node.id === id)?.label ?? id;
    cards.unshift({
      id: `${edge.source}:${edge.label}:${edge.target}`,
      title: `${name(edge.source)} → ${name(edge.target)} · ${edge.label === 'AFFILIATED_WITH' ? '机构任职关系' : edge.label}`,
      rows: edge.label === '同事关系'
        ? [['判定规则', text(d.ruleName)], ['共同机构', text(d.organization)], ['生效时段', text(d.period)]]
        : [['源数据表', text(d.source_table)], ['源记录 ID', text(d.source_record_id)], ['生效时段', text(d.period)]],
      evidence: d.evidence ?? [],
    });
  }
  return cards;
}
