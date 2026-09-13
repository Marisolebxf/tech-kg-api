import type {
  IndustryChainPanoramaQueryResponse,
  PanoramaGraphEdge,
  PanoramaGraphNode,
} from "../../api/industryChainPanorama";

/**
 * 汇总摘要中应计入的关键技术实体。
 *
 * 分层数据负责展示检索命中的技术，扩展子图还可能包含作为 anchor 的其他
 * IndustryNode/Keyword。两部分始终合并并按实体 ID 去重，保证摘要数量与
 * 左侧实际展示一致。
 */
export function collectPanoramaTechnologyLabels(
  response: IndustryChainPanoramaQueryResponse,
): string[] {
  const labels: string[] = [];
  const seen = new Set<string>();
  const add = (id: string, label: string) => {
    const normalizedLabel = label.trim();
    if (!normalizedLabel) return;
    const key = id || `label:${normalizedLabel}`;
    if (seen.has(key)) return;
    seen.add(key);
    labels.push(normalizedLabel);
  };

  const layer = response.layers.find((item) => item.key === "core_technology");
  for (const item of layer?.items ?? []) add(item.id, item.label);

  for (const node of response.graph.nodes) {
    const type = node.type.toLowerCase();
    const isTechnology =
      type.includes("industrynode") ||
      type.includes("keyword") ||
      type.includes("technology");
    if (isTechnology) add(node.id, node.label);
  }

  return labels;
}

/**
 * 摘要「产业链名称」应展示的产业链列表。
 *
 * 后端 summary.industryChains 返回图库中的产业链（如 集成电路 / 低空经济）；
 * 扩展子图也可能带出 IndustryChain 节点（如锚点本身是产业链）。两部分合并
 * 去重后展示为「集成电路等2项」样式，未输入产业关键词时仍有内容可展示。
 */
export function collectPanoramaIndustryChainLabels(
  response: IndustryChainPanoramaQueryResponse,
): string[] {
  const labels: string[] = [];
  const seen = new Set<string>();
  const add = (label: unknown) => {
    const normalizedLabel = String(label || "").trim();
    if (!normalizedLabel || seen.has(normalizedLabel)) return;
    seen.add(normalizedLabel);
    labels.push(normalizedLabel);
  };

  for (const chain of response.summary.industryChains ?? []) add(chain);

  for (const node of response.graph.nodes) {
    if (node.type.toLowerCase().includes("industrychain")) add(node.label);
  }

  return labels;
}

/**
 * 全景图全量实体口径：分层 items ∪ 子图节点，按 id 去重（子图在前，含产业链
 * 中心节点）。实体页、溯源页与画布「关系」行共用，保证各页数量一致；画布
 * 展开层仅渲染其中前若干个，不能作为全量列表的数据源。
 */
export interface PanoramaEntity {
  id: string;
  label: string;
  /** 子图节点为图库主标签（Person/Organization/...），分层实体为分层类型（technology/expert/...）。 */
  type: string;
  /** 仅分层实体携带：来源分层 key，供页面映射分层展示文案。 */
  layerKey?: string;
  sourceTable?: string | null;
  sourceField?: string | null;
  /**
   * 实体置信度：分层实体按展示指标换算（无指标回退 0.75）；子图节点图库
   * 本身没有实体置信度属性，取全部相邻边置信度的最大值（实体因子图扩展
   * 被带入，最强关系的确定性即该实体在此图中的置信度），孤立节点回退
   * 默认值 0.80。
   */
  confidence?: number;
}

/** 分层实体展示置信度：指标值换算到 0.4-1，无指标回退 0.75（画布与实体页同公式）。 */
export function panoramaLayerConfidence(
  metricValue: number | null | undefined,
): number {
  if (metricValue == null) return 0.75;
  return Math.min(1, Math.max(0.4, Number(metricValue) / 100));
}

export function collectPanoramaEntities(
  response: IndustryChainPanoramaQueryResponse,
): PanoramaEntity[] {
  // 子图节点置信度 = 全部相邻边置信度的最大值；无相邻边的孤立节点回退默认值。
  const confidenceByNode = new Map<string, number>();
  for (const edge of response.graph.edges) {
    const confidence = panoramaEdgeConfidence(edge);
    for (const id of [edge.source, edge.target]) {
      if (!id) continue;
      confidenceByNode.set(
        id,
        Math.max(confidenceByNode.get(id) ?? 0, confidence),
      );
    }
  }
  const entityById = new Map<string, PanoramaEntity>();
  for (const node of response.graph.nodes) {
    if (entityById.has(node.id)) continue;
    entityById.set(node.id, {
      id: node.id,
      label: node.label,
      type: node.type,
      sourceTable: node.sourceTable,
      sourceField: node.sourceField,
      confidence:
        confidenceByNode.get(node.id) ?? PANORAMA_EDGE_CONFIDENCE_DEFAULT,
    });
  }
  for (const layer of response.layers) {
    for (const item of layer.items) {
      if (entityById.has(item.id)) continue;
      entityById.set(item.id, {
        id: item.id,
        label: item.label,
        type: item.type,
        layerKey: layer.key,
        sourceTable: item.sourceTable,
        sourceField: item.sourceField,
        confidence: panoramaLayerConfidence(item.metricValue),
      });
    }
  }
  return [...entityById.values()];
}

/**
 * 每个实体的真实关系统计：从子图全量真实边统计（不含画布分层展示连线），
 * 格式「共 N 条：{类型} → {对端}；...」，不截断；没有真实边的实体不进入结果。
 */
export function panoramaNodeRelationSummaries(
  response: IndustryChainPanoramaQueryResponse,
  options: { edgeLabelDisplay?: (label: string) => string } = {},
): Map<string, string> {
  const labelById = new Map(
    collectPanoramaEntities(response).map((entity) => [entity.id, entity.label]),
  );
  const labelOf = (id: string) => labelById.get(id) || id;
  const relationsByNode = new Map<string, string[]>();
  const append = (id: string, text: string) => {
    const list = relationsByNode.get(id) ?? [];
    list.push(text);
    relationsByNode.set(id, list);
  };
  for (const edge of response.graph.edges) {
    const typeLabel = options.edgeLabelDisplay?.(edge.label) || edge.label;
    append(edge.source, `${typeLabel} → ${labelOf(edge.target)}`);
    append(edge.target, `${typeLabel} ← ${labelOf(edge.source)}`);
  }
  const summaries = new Map<string, string>();
  for (const [id, relations] of relationsByNode) {
    summaries.set(id, `共 ${relations.length} 条：${relations.join("；")}`);
  }
  return summaries;
}

/**
 * 图库边置信度兜底表：图库中多数边入图时未写 confidence/chain_score 属性
 * （HAS_NODE 等结构边的 schema 甚至没有该属性），页面需要展示具体数值
 * 置信度，按边类型的业务确定性给出规则推导值；有原始值时始终优先原始值。
 */
const PANORAMA_EDGE_CONFIDENCE_FALLBACK: Record<string, number> = {
  // 产业链结构关系：随产业链定义入图，结构上必然成立。
  HAS_NODE: 0.9,
  CHILD_OF: 0.9,
  DOWNSTREAM_OF: 0.9,
  SUBSIDIARY_OF: 0.9,
  LEGAL_REP_OF: 0.9,
  ACTUAL_CONTROLLER_OF: 0.9,
  BENEFICIAL_OWNER_OF: 0.9,
  // 任职/资本关联：工商等结构化源表字段，确定性较高。
  AFFILIATED_WITH: 0.85,
  EMPLOYED_BY: 0.85,
  EXECUTIVE_OF: 0.85,
  SHAREHOLDER_OF: 0.85,
  INVESTS_IN: 0.85,
  ACQUIRES: 0.85,
  FUNDED_BY: 0.85,
  // 成果关联：论文/专利 ETL 抽取，偶有实体对齐误差。
  AUTHORED_BY: 0.8,
  APPLIED_BY: 0.8,
  INVENTED_BY: 0.8,
  PUBLISHED_IN: 0.8,
  COOPERATED_WITH: 0.8,
  PAPER_COOPERATED_WITH: 0.8,
  PARTICIPATES_IN: 0.8,
  INVOLVED_IN: 0.8,
  PRODUCES: 0.8,
  BID_FOR: 0.8,
  // 资讯挂载/引用类：按关键词匹配或引用解析，误配风险相对更高。
  COVERS_CHAIN: 0.75,
  HAS_NEWS: 0.75,
  CITES: 0.75,
  CITED_BY: 0.75,
  REFERENCED_BY: 0.75,
};

/** 兜底表未覆盖的边类型统一按 0.80（与产业链 TOP-N 模块默认展示一致）。 */
const PANORAMA_EDGE_CONFIDENCE_DEFAULT = 0.8;

/**
 * 关系置信度：优先图库原始值（confidence 0-1 或 chain_score 0-100），统一
 * 换算为 0-1；图库未写值时按边类型规则推导具体数值，页面始终有值可展示。
 */
export function panoramaEdgeConfidence(edge: PanoramaGraphEdge): number {
  const direct = edge.confidence;
  const nested = edge.data?.confidence;
  const chainScore = edge.data?.chain_score;
  const raw =
    typeof direct === "number"
      ? direct
      : typeof nested === "number"
        ? nested
        : typeof chainScore === "number"
          ? chainScore / 100
          : undefined;
  if (raw === undefined || !Number.isFinite(raw)) {
    const label = String(edge.label || "").toUpperCase();
    return (
      PANORAMA_EDGE_CONFIDENCE_FALLBACK[label] ??
      PANORAMA_EDGE_CONFIDENCE_DEFAULT
    );
  }

  const normalized = raw > 1 ? raw / 100 : raw;
  return Math.min(1, Math.max(0, normalized));
}

/**
 * 选择全景图中心的真实产业链节点。
 *
 * anchorId 允许指向 IndustryNode 等任意扩图起点，但这些节点不能因此被当成
 * IndustryChain 渲染，否则同一技术节点还会在关键技术分层再次出现并重叠。
 */
export function selectPanoramaIndustryCenter(
  response: IndustryChainPanoramaQueryResponse,
  industryLabel: string,
): PanoramaGraphNode | undefined {
  const chainNodes = response.graph.nodes.filter((node) =>
    node.type.toLowerCase().includes("industrychain"),
  );
  const anchorId = String(response.input?.anchorId || "");
  const normalizedIndustry = industryLabel.trim().toLowerCase();

  return (
    chainNodes.find((node) => node.id === anchorId) ??
    chainNodes.find(
      (node) => node.label.trim().toLowerCase() === normalizedIndustry,
    ) ??
    chainNodes[0]
  );
}

/** 溯源卡片区段：与科技专家同事关系页（expert-colleague-details）同构。 */
export interface PanoramaProvenanceSection {
  title: string;
  rows: ReadonlyArray<readonly [string, string]>;
}

export interface PanoramaProvenanceCard {
  id: string;
  title: string;
  sections: PanoramaProvenanceSection[];
}

/** 实体统一取三要素行：源数据表 / 英文字段名 / 图空间 VID，缺失显示「—」。 */
function panoramaProvenanceRows(entity: {
  id: string;
  sourceTable?: string | null;
  sourceField?: string | null;
}): PanoramaProvenanceSection["rows"] {
  const text = (value: unknown) => {
    const normalized = String(value ?? "").trim();
    return normalized && normalized !== "-" ? normalized : "—";
  };
  return [
    ["源数据表", text(entity.sourceTable)],
    ["英文字段名", text(entity.sourceField)],
    ["图空间 VID", entity.id],
  ];
}

/**
 * 科技产业链全景图溯源卡片，样式与格式对齐科技专家同事关系页：
 * 实体卡为「{名称} · 实体来源」，关系卡为「{源} → {目标} · {关系类型}」，
 * 关系卡内含「源实体 / 目标实体」两个区段，各自展示三要素行。
 *
 * 实体取分层 items 与子图节点的并集（按 id 去重）；关系只取子图中的真实图库边，
 * 画布为分层展示补的虚拟中心节点与连线不在此列。未选中时返回全部实体卡 +
 * 关系卡；选中节点只返回该实体卡；选中边只返回 source/target/label 均匹配的关系卡。
 */
export function panoramaProvenanceCards(
  response: IndustryChainPanoramaQueryResponse,
  options: {
    selectedNodeId?: string;
    selectedEdge?: { source: string; target: string; label: string };
    edgeLabelDisplay?: (label: string) => string;
  } = {},
): PanoramaProvenanceCard[] {
  // 分层 items 与子图节点按 id 去重合并；子图在前（含产业链中心节点）。
  const entities = collectPanoramaEntities(response);
  const entityById = new Map(entities.map((entity) => [entity.id, entity]));

  const nodeCards: PanoramaProvenanceCard[] = [
    ...entities.map((entity) => ({
      id: `node:${entity.id}`,
      title: `${entity.label || entity.id} · 实体来源`,
      sections: [
        { title: "", rows: panoramaProvenanceRows(entity) },
      ] satisfies PanoramaProvenanceSection[],
    })),
  ];

  const labelOf = (id: string) => entityById.get(id)?.label || id;
  const buildEdgeCard = (edge: PanoramaGraphEdge, index: number): PanoramaProvenanceCard => {
    const relationName = options.edgeLabelDisplay?.(edge.label) || edge.label;
    return {
      id: `edge:${index}:${edge.source}:${edge.target}`,
      title: `${labelOf(edge.source)} → ${labelOf(edge.target)} · ${relationName}`,
      sections: [
        {
          title: `源实体：${labelOf(edge.source)}`,
          rows: panoramaProvenanceRows(
            entityById.get(edge.source) ?? { id: edge.source },
          ),
        },
        {
          title: `目标实体：${labelOf(edge.target)}`,
          rows: panoramaProvenanceRows(
            entityById.get(edge.target) ?? { id: edge.target },
          ),
        },
      ] satisfies PanoramaProvenanceSection[],
    };
  };
  const edgeCards: PanoramaProvenanceCard[] = response.graph.edges.map(
    (edge, index) => buildEdgeCard(edge, index),
  );

  const { selectedNodeId, selectedEdge } = options;
  if (selectedNodeId) {
    const card = nodeCards.find((card) => card.id === `node:${selectedNodeId}`);
    return card ? [card] : [];
  }
  if (selectedEdge) {
    return response.graph.edges
      .map((edge, index) => ({ edge, index }))
      .filter(
        ({ edge }) =>
          edge.source === selectedEdge.source &&
          edge.target === selectedEdge.target &&
          edge.label === selectedEdge.label,
      )
      .map(({ edge, index }) => buildEdgeCard(edge, index));
  }
  return [...nodeCards, ...edgeCards];
}
