export interface ActualServiceRule { name: string; type: string; target: string; trigger: string; logic: string; output: string; threshold: string; audit: string }

const audit = '代码未配置人工审核流；查询异常或未命中时按接口实际状态返回，不补造业务结果。'
const make = (name: string, type: string, target: string, trigger: string, logic: string, output: string, threshold: string): ActualServiceRule => ({ name, type, target, trigger, logic, output, threshold, audit })

export const actualServiceRules: Record<string, ActualServiceRule[]> = {
  'expert-direct': [make('COAUTHOR_WITH 直接关系查询', '图关系查询规则', 'Person 节点、COAUTHOR_WITH 边', '输入专家 A，可选专家 B、机构和时间', '解析专家标识或姓名，读取 COAUTHOR_WITH 边并补齐对端 Person 属性；机构关键词命中任一端时保留，按共同论文数排序。', '直接关系明细、专家节点、合作边和数据溯源', 'limit 限制为 1–100；代码未设置语义相似度阈值')],
  'node-indirect': [
    make('间接路径发现规则', '路径查询规则', '核心 Person 节点及深度范围内的真实节点和关系边', '核心节点可定位，path_depth 为 2 或 3', '读取核心节点双向子图；同类型、同端点的边仅保留强度较高者；枚举不重复节点的简单路径，仅保留不少于 2 跳且终点不是核心节点直接邻居的路径。', '直接节点、间接节点、完整路径节点和关系边', '子图最多 200 项、候选路径最多 1000 条、最终最多 50 条'),
    make('间接关系分类规则', '关系类型映射规则', '候选路径中的真实关系边类型', '简单路径达到 2 跳或 3 跳', '按项目、专利、产业、机构、学术关系边集合依次归类；再按请求选择的学术关联、机构关联或项目关联过滤。', '路径关系类型及分类计数', 'relation_types 必须且只能选择学术关联、机构关联、项目关联中的一项'),
    make('路径强度计算与排序规则', '评分过滤规则', '候选路径及其关系边', '路径完成关系分类后', '边强度优先读取 confidence、score、relation_strength；百分制值除以 100。缺失时按合作次数对数归一化，再缺失时使用边类型默认权重。路径强度取边强度几何平均并乘以 0.92 的长度衰减。', '路径强度、平均强度、最大强度及降序结果', '路径强度 >= min_strength（默认 0.65）；同一目标和边类型序列仅保留最强路径'),
  ],
  'two-point-achievement': [make('共同成果交集', '成果关联规则', '两位专家及论文、专利、项目', '输入两位专家及成果类型', '分别读取两位专家的成果边，按成果实体 ID 求交集，再按 paper/patent/project 筛选并排序；缺失字段不编造。', '共同成果、类型统计、合作模式和图谱', '每类最多 limitPerType 条；跨度 >= 3 年且总量 >= 3 判长期稳定')],
  'expert-colleague': [make('任职区间重叠', '同事关系判定规则', '专家、机构、部门/团队和任职边', '输入两位专家及可选筛选条件', '查找共同任职机构或部门并计算任职月份交集；共同团队/项目及有效期内成果参与置信度加权，按置信度和成果数降序。', '同事关系、有效时段、重叠月份、证据和置信度', '至少重叠 1 个月；confidence >= min_confidence')],
  'expert-alumni': [make('教育经历同校匹配', '校友关系判定规则', '专家及教育经历', '输入专家及可选学校、阶段、目标专家', '标准化学校名称后匹配共同学校，根据阶段和就读日期交集补充同届/同期维度；互动边仅用于统计。', '校友、共同院校、维度、互动统计和图谱', '同校为必要条件；无互动边时互动计数为 0')],
  'paper-cooperation': [
    make('共同署名论文查询规则', '图路径查询规则', '两位专家、AUTHORED/AUTHORED_BY 作者边和 Paper 节点', 'expertAId 与 expertBId 均可定位且不是同一专家', '查询专家 A→论文→专家 B 的真实作者路径，按论文 ID 去重；时间条件仅取 startTime/endTime 的年份过滤 publication_year。无时间条件且未命中逐篇论文时，回退读取 COAUTHOR_WITH 合作边统计。', '合作论文数量、作者列表、作者单位和合作年份范围', '逐篇论文最多 1000 篇；代码未配置 status=1、作者匹配置信度或关系验证置信度过滤'),
    make('论文指标与合作成员统计规则', '事实聚合规则', '共同论文及其 PUBLISHED_IN、HAS_KEYWORD、CITED_BY、作者关系', '命中共同论文路径', '主题按关键词出现次数取前 8；期刊/会议按论文类型和场馆分级属性统计；被引数依次读取论文 citation_count、作者边 citations、CITED_BY 边数量；共同作者按共同论文次数排序取前 5。', '论文主题、期刊/会议级别、总被引、最高单篇被引和核心合作人员', '稳定团队成员须共同论文数 >= 2 且至少覆盖 2 个不同发表年份'),
    make('学术影响力与共同贡献计算规则', '评分标注规则', '合作论文数、合作论文被引数和已分级论文数', '论文指标统计完成后', '学术影响力=min(99.5, 论文数×6.5 + 总被引/max(18, 论文数×3) + 已分级论文数×4)。根据是否有论文、被引、跨机构和主题生成共同贡献标签。', 'academicImpactScore、cooperationFrequency 和 sharedContribution', '无合作论文时影响力为 0；代码未配置平均场馆得分 70 或高影响论文淘汰阈值'),
  ],
  'enterprise-relation': [make('专家—企业两跳关系', '限定边类型子图规则', '专家、企业及治理/项目/专利关系', '输入 expert_id 及可选企业筛选', '查询 depth=2 子图，仅使用代码列出的 12 类治理、任职、项目和专利边；应用请求筛选并按置信度排序，对首要企业补查风险事件。', '企业关系、角色、技术领域、风险摘要和置信度', '子图 limit=50；置信度来自 COOPERATION_CONFIDENCE 映射')],
  'industry-chain-event': [make('产业链事件影响力 TOP-N', '事件筛选排序规则', '产业链节点、企业、事件和资讯', '输入 chain_node_id、top_n 及可选筛选', '按 chain_score 选前 max_orgs 家企业，并行读取事件和资讯；筛选去重后，以事件类型权重、金额、新鲜度和 chain_score 计算影响力并取 TOP-N。', 'TOP 事件、影响力、关联实体、风险、趋势和机遇', '数量 <= top_n；企业数 <= max_orgs；风险置信度由风险等级映射')],
  'industry-chain-panorama': [make('产业链四层聚合', '分层图谱查询规则', '产业链、技术、企业、专家和成果', '输入产业链 ID 或主题及各层 limit', '定位中心节点并按真实标签和关系展开子图，将实体归入核心技术、领军企业、领军专家、代表成果四层，保留溯源属性。', '四层实体、统计、子图和溯源', '各层数量受 limit 控制；代码未配置统一置信度淘汰阈值')],
}
