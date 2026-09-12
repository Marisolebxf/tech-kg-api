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

interface ProvenanceSection {
  title: string;
  rows: Row[];
}

function provenanceSection(node: ColleagueGraphNode, title: string): ProvenanceSection {
  const p = node.data?.provenance ?? {};
  const details = node.data?.details ?? {};
  const value = (...values: unknown[]) => values
    .map(item => item == null ? '' : String(item).trim())
    .find(item => item && item !== '-' && item !== '未提供') ?? '';
  const rows: Row[] = [
    ['源数据表', value(details.source_table, p.sourceTable, details.organization_base)],
    ['英文字段名', value(details.source_field, p.sourceField)],
    ['图空间 VID', node.id],
  ];
  return { title, rows };
}

export function colleagueProvenanceCards(
  nodes: ColleagueGraphNode[], edges: ColleagueGraphEdge[],
  selectedId?: string,
  selectedEdge?: Pick<ColleagueGraphEdge, 'source' | 'target' | 'label'>,
): Array<{ id: string; title: string; sections: ProvenanceSection[] }> {
  const byId = new Map(nodes.map(node => [node.id, node]));
  const visibleNodes = selectedId ? nodes.filter(node => node.id === selectedId) : selectedEdge ? [] : nodes;
  const visibleEdges = selectedId ? [] : selectedEdge
    ? edges.filter(edge => edge.source === selectedEdge.source && edge.target === selectedEdge.target && edge.label === selectedEdge.label)
    : edges;
  return [
    ...visibleNodes.map(node => ({
      id: `node:${node.id}`,
      title: `${node.label} · 实体来源`,
      sections: [provenanceSection(node, '')],
    })),
    ...visibleEdges.map((edge, index) => {
      const source = byId.get(edge.source) ?? { id: edge.source, label: edge.source, type: '' };
      const target = byId.get(edge.target) ?? { id: edge.target, label: edge.target, type: '' };
      return {
        id: `edge:${edge.id ?? index}:${edge.source}:${edge.target}`,
        title: `${source.label} → ${target.label} · ${edge.label === 'AFFILIATED_WITH' ? '机构任职关系' : edge.label}`,
        sections: [
          provenanceSection(source, `源实体：${source.label}`),
          provenanceSection(target, `目标实体：${target.label}`),
        ],
      };
    }),
  ];
}
