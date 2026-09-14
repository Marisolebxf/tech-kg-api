import type {
  IndustryChainPanoramaQueryResponse,
  PanoramaGraphEdge,
  PanoramaGraphNode,
} from "../../api/industryChainPanorama";

/**
 * 全量口径的关键技术实体标签（分层 items ∪ 子图技术节点，按实体 ID 去重）。
 *
 * 注意：页面摘要「关键技术」数量已改为按画布渲染节点统计（与画布一致），
 * 本函数保留作为全量口径的工具集合，不再是摘要计数依据。
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
 * 中心节点）。作为实体元数据（置信度、溯源三要素）的统一来源；实体页与
 * 溯源页按画布可见节点过滤后使用，展示数量与画布渲染的节点一致。
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
 * 每个实体的关系统计：默认从子图全量真实边统计（不含画布分层展示连线）；
 * 页面按画布口径调用时通过 options.edges 传入实际渲染的连线（可含分层
 * 展示连线），统计范围随之收窄；端点名可用 options.labelById 覆盖（画布
 * 节点标签）。格式「{类型} → {对端}；...」，不带总数前缀，不截断；没有连线的
 * 实体不进入结果。
 */
export function panoramaNodeRelationSummaries(
  response: IndustryChainPanoramaQueryResponse,
  options: {
    edgeLabelDisplay?: (label: string) => string;
    /** 关系统计口径；缺省为子图全量真实边。 */
    edges?: PanoramaGraphEdge[];
    /** 端点 id → 展示名；缺省从全量实体并集取。画布口径传画布节点标签，
     * 让虚拟中心等不在并集里的展示元素也能显示名称。 */
    labelById?: Map<string, string>;
  } = {},
): Map<string, string> {
  // 全量实体并集的标签；调用方传 labelById（画布口径）时优先使用。
  const fallbackLabels = new Map(
    collectPanoramaEntities(response).map((entity) => [entity.id, entity.label]),
  );
  const labelOf = (id: string) =>
    options.labelById?.get(id) ?? fallbackLabels.get(id) ?? id;
  const relationsByNode = new Map<string, string[]>();
  const append = (id: string, text: string) => {
    const list = relationsByNode.get(id) ?? [];
    list.push(text);
    relationsByNode.set(id, list);
  };
  for (const edge of options.edges ?? response.graph.edges) {
    const typeLabel = options.edgeLabelDisplay?.(edge.label) || edge.label;
    append(edge.source, `${typeLabel} → ${labelOf(edge.target)}`);
    append(edge.target, `${typeLabel} ← ${labelOf(edge.source)}`);
  }
  const summaries = new Map<string, string>();
  for (const [id, relations] of relationsByNode) {
    summaries.set(id, relations.join("；"));
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
    // 页面内部合成 id（如虚拟产业链中心 __panorama_center__）不是图空间 VID。
    ["图空间 VID", entity.id.startsWith("__") ? "—" : entity.id],
  ];
}

/**
 * 科技产业链全景图溯源卡片，样式与格式对齐科技专家同事关系页：
 * 实体卡为「{名称} · 实体来源」，关系卡为「{源} → {目标} · {关系类型}」，
 * 关系卡内含「源实体 / 目标实体」两个区段，各自展示三要素行。
 *
 * 实体取分层 items 与子图节点的并集（按 id 去重），关系取真实图库边；传入
 * visibleNodeIds / edges（画布口径）时实体卡与关系卡都收窄到画布渲染范围，
 * 画布为分层展示补的虚拟中心节点不在此列。未选中时返回全部实体卡 +
 * 关系卡；选中节点只返回该实体卡；选中边只返回 source/target/label 均匹配
 * 的关系卡——选中边在 matchEdges（缺省用 edges）内匹配，画布口径传全部
 * 连线时点击分层展示连线也能出两端实体的溯源卡。
 */
export function panoramaProvenanceCards(
  response: IndustryChainPanoramaQueryResponse,
  options: {
    selectedNodeId?: string;
    selectedEdge?: { source: string; target: string; label: string };
    edgeLabelDisplay?: (label: string) => string;
    /** 画布口径：仅这些 id 的实体生成实体卡；缺省为全量实体。 */
    visibleNodeIds?: Set<string>;
    /** 关系卡数据源（未选中时展示），缺省为子图全量真实边。 */
    edges?: PanoramaGraphEdge[];
    /** 选中边匹配池，缺省用 edges。画布口径传全部连线（含分层展示连线，
     * data.inferred 标记），让点击虚拟连线也能出两端实体溯源卡（卡内注明
     * 连线性质）。 */
    matchEdges?: PanoramaGraphEdge[];
    /** 端点 id → 展示名（画布口径传画布节点标签）；缺省从实体并集取。
     * 虚拟产业链中心等不在并集里的展示元素也能显示产业名，而不是内部
     * 合成 id。 */
    labelById?: Map<string, string>;
  } = {},
): PanoramaProvenanceCard[] {
  // 分层 items 与子图节点按 id 去重合并；子图在前（含产业链中心节点）。
  // 传入 visibleNodeIds（画布口径）时只保留画布渲染的实体。
  const entities = collectPanoramaEntities(response).filter(
    (entity) => !options.visibleNodeIds || options.visibleNodeIds.has(entity.id),
  );
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

  const labelOf = (id: string) =>
    options.labelById?.get(id) ?? entityById.get(id)?.label ?? id;
  /** 关系端点实体：不在实体并集里的页面合成展示元素（如虚拟产业链中心
   * __panorama_center__）按「查到即记」派生口径记录来源——宿主是查询
   * 入参，不编造图库数据；其余未知 id 维持占位回退。 */
  const endpointEntity = (id: string) =>
    entityById.get(id) ??
    (id.startsWith("__")
      ? {
          id,
          label: labelOf(id),
          type: "页面展示元素",
          sourceTable: "页面合成 · 查询入参",
          sourceField: "industry",
        }
      : { id });
  const buildEdgeCard = (edge: PanoramaGraphEdge, index: number): PanoramaProvenanceCard => {
    const relationName = options.edgeLabelDisplay?.(edge.label) || edge.label;
    return {
      id: `edge:${index}:${edge.source}:${edge.target}`,
      title: `${labelOf(edge.source)} → ${labelOf(edge.target)} · ${relationName}`,
      sections: [
        {
          title: `源实体：${labelOf(edge.source)}`,
          rows: panoramaProvenanceRows(endpointEntity(edge.source)),
        },
        {
          title: `目标实体：${labelOf(edge.target)}`,
          rows: panoramaProvenanceRows(endpointEntity(edge.target)),
        },
      ] satisfies PanoramaProvenanceSection[],
    };
  };
  const scopedEdges = options.edges ?? response.graph.edges;
  const edgeCards: PanoramaProvenanceCard[] = scopedEdges.map(
    (edge, index) => buildEdgeCard(edge, index),
  );

  const { selectedNodeId, selectedEdge } = options;
  if (selectedNodeId) {
    const card = nodeCards.find((card) => card.id === `node:${selectedNodeId}`);
    return card ? [card] : [];
  }
  if (selectedEdge) {
    return (options.matchEdges ?? scopedEdges)
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
