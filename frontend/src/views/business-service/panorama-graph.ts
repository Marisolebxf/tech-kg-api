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

/** 读取新版或历史缓存响应中的关系置信度，并统一为 0-1。 */
export function panoramaEdgeConfidence(
  edge: PanoramaGraphEdge,
): number | undefined {
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
  if (raw === undefined || !Number.isFinite(raw)) return undefined;

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
