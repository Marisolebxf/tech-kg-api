export interface ActualServiceRule {
  name: string;
  type: string;
  target: string;
  trigger: string;
  logic: string;
  output: string;
  threshold: string;
  audit: string;
}

const audit =
  "代码未配置人工审核流；查询异常或未命中时按接口实际状态返回，不补造业务结果。";

const bidAlgorithmNames: Record<string, string> = {
  "expert-direct": "语义匹配与关系验证算法",
  "node-indirect": "路径分析与关系传递算法",
  "two-point-achievement": "成果关联与归因算法",
  "expert-colleague": "任职时间匹配与团队归属算法",
  "expert-alumni": "教育经历匹配算法",
  "paper-cooperation": "作者关联与合作频次算法",
  "enterprise-relation": "企业关联与角色定位算法",
  "industry-chain-event": "事件影响力评估算法",
  "industry-chain-panorama": "产业链架构建模与可视化算法",
};

const bidAlgorithmRules: Record<
  string,
  Omit<ActualServiceRule, "name" | "type">
> = {
  "expert-direct": {
    target: "专家 Person 节点及 COAUTHOR_WITH 合作边",
    trigger: "输入专家 A，可选专家 B、机构和时间范围",
    logic:
      "按专家标识定位节点，未命中时按中英文姓名精确匹配。读取合著关系后，按机构和关系时间过滤，并根据共同论文数生成关系强度与说明。",
    output: "直接关系、关系时间、共同论文数、关系强度及溯源",
    threshold:
      "最多返回 1–100 条；关系强度限制在 60–99。当前未实现向量语义相似度；同时输入 A/B 时会查询两人的合著网络，不强制只保留 A—B 关系。",
    audit,
  },
  "node-indirect": {
    target: "核心专家及其 2–3 跳真实关系子图",
    trigger: "核心专家可定位，并选择关系类型、路径深度和最低强度",
    logic:
      "枚举不重复节点的 2–3 跳路径，排除核心专家的一跳邻居。根据路径中的边类型标注关系类别，综合各边强度和路径长度计算路径强度，再过滤、去重并排序。",
    output: "间接节点、关系类型、传递路径和路径强度",
    threshold:
      "路径深度为 2 或 3；路径强度不低于 min_strength（默认 0.65）；最多返回 50 条路径。",
    audit,
  },
  "two-point-achievement": {
    target: "两位专家共同关联的论文、专利和项目",
    trigger: "输入两位不同且可定位的专家，可选成果类型和时间范围",
    logic:
      "分别读取两位专家的成果关系，按成果节点 ID 求交集。对共同成果分类统计并补充时间、领域、奖项等信息，再根据成果类型、数量和年份跨度归纳核心贡献与合作模式。",
    output: "共同成果清单、分类统计、核心贡献和合作模式",
    threshold:
      "每类最多返回 limitPerType 条；成果跨度不少于 3 年且总量不少于 3 时标记为长期稳定合作。",
    audit,
  },
  "expert-colleague": {
    target: "专家任职边、机构层级、部门/团队及共同成果",
    trigger: "输入核心专家，可选目标专家、机构、部门、团队、时间和最低置信度",
    logic:
      "匹配共同任职机构或其一跳上下级机构，并计算双方任职时间的交集。部门、共同团队、合著和共同成果用于补充协作场景及关系置信度，最后按置信度筛选排序。",
    output: "同事关系、生效时段、共同机构/团队、协作场景、期间成果和置信度",
    threshold:
      "双方任职时间必须可解析且至少重叠 1 个月；结果置信度不低于 min_confidence。",
    audit,
  },
  "expert-alumni": {
    target: "专家教育院校、学历和就读时间字段",
    trigger: "输入核心专家，可选目标专家、学校、教育阶段和返回数量",
    logic:
      "解析并规范化双方教育经历，通过院校名称相等或互相包含识别同校关系。学历相同标注“同学历”，就读年份相交标注“同期”，命中后再统计共同论文、专利和项目。",
    output: "校友关系、共同院校、匹配维度及后续互动统计",
    threshold:
      "同校是必要条件；列表模式最多返回 limit 条。缺少教育经历时不生成校友关系。",
    audit,
  },
  "paper-cooperation": {
    target: "两位专家共同署名的论文及作者、期刊、关键词和引用关系",
    trigger: "输入两位不同且可定位的专家，可选发表时间范围",
    logic:
      "查询两位专家共同署名的论文并按论文 ID 去重，再统计合作次数、发表年份、主题、期刊/会议和引用情况。共同作者按合作论文数排序，跨多个年份持续合作的成员标记为稳定团队。",
    output: "合作论文、合作频次、研究主题、发表层级、引用情况和核心合作人员",
    threshold:
      "逐篇论文最多查询 1000 篇；稳定团队成员需共同论文不少于 2 篇且覆盖至少 2 个发表年份。",
    audit,
  },
  "enterprise-relation": {
    target: "专家、科技企业及治理任职、项目和专利关系",
    trigger: "输入专家，可选企业名称、角色、行业和重点企业筛选",
    logic:
      "查询专家两跳子图，识别直接治理任职，以及经项目或专利连接的企业。按企业属性和请求条件过滤，并依据职位文本确定角色层级，同时补充合作时间、领域、企业背景和首要企业风险摘要。",
    output:
      "专家—企业关系、角色及层级、合作类型、时间、领域、企业背景和风险摘要",
    threshold:
      "子图最多取 50 项；治理、项目、专利关系固定置信度分别为 0.9、0.8、0.8；风险查询失败不影响主结果。",
    audit,
  },
  "industry-chain-event": {
    target: "产业链节点关联企业的事件和资讯",
    trigger: "输入产业链节点、TOP-N 数量，可选事件类型、时间范围和企业扫描数",
    logic:
      "优先选择产业链得分较高的企业，汇总并去重其事件。综合事件类型、金额、发生时间和产业链得分计算影响力，排序取 TOP-N，再关联相关企业和治理专家，并生成风险、趋势与机遇说明。",
    output: "TOP-N 事件、影响力排名、关联企业/专家、风险等级、趋势和机遇",
    threshold:
      "返回数量不超过 top_n，扫描企业数不超过 max_orgs；时间新鲜度以 2026 年为基准，最低为 0.3。",
    audit,
  },
  "industry-chain-panorama": {
    target: "产业链中的技术、企业、专家、成果及其真实关系",
    trigger: "输入产业关键词或锚点，可选展开深度和每层数量",
    logic:
      "将命中的实体归入核心技术、领军企业、领军专家和代表成果四层。以指定锚点或首个可用实体展开子图，并对节点和关系去重后生成可视化数据；关键词精确匹配失败时再做有限范围的包含匹配。",
    output: "四层产业实体、统计信息、可视化节点/关系和溯源",
    threshold:
      "每层最多 20 项，子图深度为 1–3；结果缓存 600 秒。当前指标仅展示，不作为统一淘汰分数。",
    audit,
  },
};

// 每个模块只展示标书指定算法；说明按后端当前真实实现维护。
export const actualServiceRules: Record<string, ActualServiceRule[]> =
  Object.fromEntries(
    Object.keys(bidAlgorithmNames).map((key) => [
      key,
      [
        {
          ...bidAlgorithmRules[key],
          name: bidAlgorithmNames[key],
          type: "标书要求算法",
        },
      ],
    ]),
  );
