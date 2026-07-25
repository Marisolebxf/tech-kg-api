<script setup lang="ts">
import { computed, ref } from 'vue'

type Entity = { name: string; label: string; level: '核心实体' | '支撑实体'; key: string; source: string; description: string }
type Relation = { name: string; label: string; source: string; target: string; basis: string; level?: '标准' | '扩展' }

const activeTab = ref('标准实体')
const keyword = ref('')
// 版本记录（已隐藏）
// const schemaVersionMessage = ref('')
const tabs = ['标准实体', '事实关系', '推理关系', '属性定义']

const entities: Entity[] = [
  { name: 'Expert', label: '专家 / 人才 / 学者', level: '核心实体', key: 'scholar_id / expert_id', source: 'dwd_scholar / dwd_paper_author / dwd_project_person / dwd_patent_inventor', description: '统一承载科研与产业人才主体' },
  { name: 'Organization', label: '机构 / 企业', level: '核心实体', key: 'org_id / external_id / credit_code', source: 'dwd_org_reg_info / dwd_forg_base_info / dwd_paper_affiliation / dwd_patent_applicant', description: '高校、科研机构、企业、医院和政府机构统一建模，用 org_category 区分' },
  { name: 'Paper', label: '论文', level: '核心实体', key: 'DOI / paper_id', source: 'dwd_zh_paper_detail / dwd_en_paper_detail / dwd_paper_reference', description: '论文成果与引用信息' },
  { name: 'Project', label: '项目', level: '核心实体', key: 'id / project_number', source: 'dwd_zh_project / dwd_en_project / dwd_project_output', description: '科研项目、资助、参与人员与项目成果' },
  { name: 'Patent', label: '专利', level: '核心实体', key: 'patent_id / publication_number / application_number', source: 'dwd_patent / dwd_patent_inventor / dwd_patent_applicant', description: '专利成果、法律状态、权利人与技术分类' },
  { name: 'Report', label: '报告', level: '核心实体', key: 'report_id', source: 'dwd_zh_report / dwd_en_report / dwd_report_author', description: '科技报告及其作者、机构、论文和项目关联' },
  { name: 'Policy', label: '政策', level: '核心实体', key: 'id / recordId / URL', source: 'dws_zck_policy / dwd_zck_intl_policy / dwd_policy_department', description: '政策文本、发布部门、领域与产业链节点' },
  { name: 'Event', label: '事件 / 资讯', level: '核心实体', key: 'news_id / URL / 生成 ID', source: 'dwd_org_important_news_info / dwd_industry_chain_news_info / dwd_financing_event', description: '用 event_type 区分资讯、融资、投资、并购、政策等事件' },
  { name: 'IndustryChainNode', label: '产业链节点', level: '核心实体', key: 'chain_code + node_id', source: 'dwd_industry_chain_info', description: '产业链的上游、中游、下游及具体环节' },
  { name: 'Product', label: '产品 / 技术产品', level: '核心实体', key: '产品 ID / 标准产品名', source: 'dwd_org_industry_chain_prod_dtl', description: '企业产品、技术产品与产业链节点' },
  { name: 'ResearchField', label: '研究方向 / 技术领域', level: '核心实体', key: 'field_id / discipline_code / 标准名', source: 'dim_research_field / dim_discipline_code / dim_ipc', description: '统一研究方向、学科、关键词、IPC 与产业技术领域' },
  { name: 'Person', label: '通用人员', level: '支撑实体', key: 'person_id', source: 'dwd_org_executive / dwd_org_shareholder / dwd_patent_inventor / dwd_paper_author', description: '已确认为同一自然人，但不能确认为专家时使用' },
  { name: 'Publication', label: '期刊 / 会议 / 出版物', level: '支撑实体', key: 'ISSN / EISSN / publication_id', source: 'dim_publication / dwd_journal', description: '论文发表载体及其动态指标' },
  { name: 'IndustryChain', label: '产业链', level: '支撑实体', key: 'chain_code', source: 'dim_industry_chain / dwd_industry_chain_info', description: '表示整条产业链，与 IndustryChainNode 明确分层' },
]

const factRelations: Relation[] = [
  { name: 'HAS_RESEARCH_FIELD', label: '专家研究方向', source: 'Expert', target: 'ResearchField', basis: '专家方向拆分、标准化' },
  { name: 'PUBLISH', label: '发表论文', source: 'Expert', target: 'Paper', basis: '作者对齐后生成，保留作者顺序' },
  { name: 'WORKS_AT', label: '任职', source: 'Expert / Person', target: 'Organization', basis: '工作经历抽取机构、职位和时间' },
  { name: 'STUDY_AT', label: '就读', source: 'Expert / Person', target: 'Organization', basis: '教育背景抽取学校、专业、学历和时间' },
  { name: 'AFFILIATED_WITH', label: '作者发表时单位', source: 'Expert / Person', target: 'Organization', basis: '论文作者单位对齐后生成' },
  { name: 'PUBLISHED_IN', label: '论文发表于', source: 'Paper', target: 'Publication', basis: 'ISSN、EISSN 或出版物名对齐' },
  { name: 'CITES', label: '论文引用', source: 'Paper', target: 'Paper', basis: 'DOI、论文 ID 或题名作者对齐' },
  { name: 'REFERENCES', label: '论文参考', source: 'Paper', target: 'Paper', basis: '参考文献对齐后生成' },
  { name: 'PAPER_FIELD', label: '论文研究方向', source: 'Paper', target: 'ResearchField', basis: '关键词与学科分类归一' },
  { name: 'SHAREHOLDER_OF', label: '股东关系', source: 'Organization / Person', target: 'Organization', basis: '股东名称对齐，保留持股比例' },
  { name: 'SUBSIDIARY_OF', label: '子公司关系', source: 'Organization', target: 'Organization', basis: '子公司对齐后生成' },
  { name: 'EXECUTIVE_OF', label: '高管任职', source: 'Expert / Person', target: 'Organization', basis: '高管姓名、职务和机构对齐' },
  { name: 'HAS_PRODUCT', label: '企业拥有产品', source: 'Organization', target: 'Product', basis: '产品拆分、标准化后生成' },
  { name: 'HAS_EVENT', label: '主体发生事件', source: 'Organization', target: 'Event', basis: '企业与资讯、融资、并购等事件连接' },
  { name: 'LEAD_PROJECT', label: '主持项目', source: 'Expert', target: 'Project', basis: '项目主持人对齐后生成' },
  { name: 'PARTICIPATE_IN', label: '参与项目', source: 'Expert / Person', target: 'Project', basis: '参与者拆分对齐后生成' },
  { name: 'FUNDED_BY', label: '项目受资助', source: 'Project', target: 'Organization', basis: '资助机构对齐后生成' },
  { name: 'PARTICIPATE_IN_PROJECT', label: '机构参与项目', source: 'Organization', target: 'Project', basis: '参与机构拆分对齐后生成' },
  { name: 'PROJECT_FIELD', label: '项目研究方向', source: 'Project', target: 'ResearchField', basis: '学科代码优先，关键词辅助' },
  { name: 'PROJECT_OUTPUT_PAPER', label: '项目产出论文', source: 'Project', target: 'Paper', basis: 'DOI 或 paper_id 对齐' },
  { name: 'PROJECT_OUTPUT_PATENT', label: '项目产出专利', source: 'Project', target: 'Patent', basis: '专利号或 patent_id 对齐' },
  { name: 'PROJECT_OUTPUT_REPORT', label: '项目产出报告', source: 'Project', target: 'Report', basis: '报告对齐后生成' },
  { name: 'INVENT_PATENT', label: '发明专利', source: 'Expert / Person', target: 'Patent', basis: '发明人对齐后生成' },
  { name: 'APPLY_PATENT', label: '申请专利', source: 'Organization / Person', target: 'Patent', basis: '申请人对齐后生成' },
  { name: 'OWN_PATENT', label: '拥有专利', source: 'Organization / Person', target: 'Patent', basis: '当前权利人对齐后生成' },
  { name: 'PATENT_FIELD', label: '专利技术方向', source: 'Patent', target: 'ResearchField', basis: 'IPC / IPCR / CPC 分类标准化' },
  { name: 'PATENT_CITES', label: '专利引用', source: 'Patent', target: 'Patent', basis: '被引用专利对齐后生成' },
  { name: 'AUTHOR_OF_REPORT', label: '报告作者', source: 'Expert / Person', target: 'Report', basis: '报告作者对齐后生成' },
  { name: 'REPORT_ORG', label: '报告机构', source: 'Report', target: 'Organization', basis: '完成单位对齐后生成' },
  { name: 'REPORT_RELATED_PAPER', label: '报告关联论文', source: 'Report', target: 'Paper', basis: '相关文献对齐' },
  { name: 'REPORT_RELATED_PROJECT', label: '报告关联项目', source: 'Report', target: 'Project', basis: '相关项目对齐' },
  { name: 'REPORT_FIELD', label: '报告研究方向', source: 'Report', target: 'ResearchField', basis: '关键词标准化' },
  { name: 'POLICY_RELATED_FIELD', label: '政策关联领域', source: 'Policy', target: 'ResearchField', basis: '关键词、全要素和正文抽取' },
  { name: 'POLICY_RELATED_CHAIN_NODE', label: '政策关联产业链节点', source: 'Policy', target: 'IndustryChainNode', basis: '关键词与语义匹配' },
  { name: 'POLICY_PUBLISHED_BY', label: '政策发布部门', source: 'Policy', target: 'Organization', basis: '发布部门对齐后生成' },
  { name: 'HAS_CHAIN_NODE', label: '产业链包含节点', source: 'IndustryChain', target: 'IndustryChainNode', basis: 'chain_code + node_id' },
  { name: 'PARENT_OF', label: '产业链父子节点', source: 'IndustryChainNode', target: 'IndustryChainNode', basis: 'parent_id 指向 node_id' },
  { name: 'UPSTREAM_DOWNSTREAM', label: '产业链上下游', source: 'IndustryChainNode', target: 'IndustryChainNode', basis: 'downstream_link_code 生成' },
  { name: 'BELONGS_TO_CHAIN_NODE', label: '企业属于产业链节点', source: 'Organization', target: 'IndustryChainNode', basis: '企业对齐后保留 chain_score' },
  { name: 'PRODUCT_CHAIN_NODE', label: '产品关联产业链节点', source: 'Product', target: 'IndustryChainNode', basis: '标准产品连接所属节点' },
  { name: 'RELATED_EVENT', label: '产业链节点关联事件', source: 'IndustryChainNode', target: 'Event', basis: '产业链资讯生成事件' },
  { name: 'ORG_FIELD', label: '企业技术领域', source: 'Organization', target: 'ResearchField', basis: '行业分类、经营范围和产品领域归一' },
  { name: 'HAS_FINANCIAL_RECORD', label: '机构年度财务', source: 'Organization', target: 'FinancialRecord', basis: '需要保留年度历史时生成', level: '扩展' },
  { name: 'BELONGS_TO_PATENT_FAMILY', label: '专利属于家族', source: 'Patent', target: 'PatentFamily', basis: '专利家族对齐后生成', level: '扩展' },
]

const inferenceRelations: Relation[] = [
  { name: 'CO_AUTHOR', label: '论文合作', source: 'Expert', target: 'Expert', basis: '共同发表同一论文' },
  { name: 'COLLEAGUE', label: '同事关系', source: 'Expert', target: 'Expert', basis: '同一机构任职且时间重叠，或共同参与项目' },
  { name: 'ALUMNI', label: '校友关系', source: 'Expert', target: 'Expert', basis: '同校就读，结合专业、学历和时间' },
  { name: 'DIRECT_RELATION', label: '专家直接关系', source: 'Expert', target: 'Expert', basis: '论文、项目、专利、同事、校友和企业合作综合判定' },
  { name: 'INDIRECT_RELATION', label: '专家间接关系', source: 'Expert', target: '其他实体', basis: '基于标准事实关系做多跳路径分析' },
  { name: 'COOPERATIVE_OUTPUT', label: '合作成果', source: 'Expert', target: 'Achievement 视图', basis: '共同论文、专利、项目和报告统计' },
  { name: 'EXPERT_COMPANY_RELATION', label: '专家企业关系', source: 'Expert', target: 'Organization', basis: '任职、专利、项目、高管与产品领域综合判定' },
  { name: 'CHAIN_EVENT_IMPACT', label: '产业链事件影响', source: 'IndustryChainNode', target: 'Event', basis: '事件热度、关联企业数、政策影响和趋势' },
  { name: 'CHAIN_OVERVIEW_RELATION', label: '产业链全景关联', source: 'IndustryChainNode', target: '多类实体', basis: '节点、企业、产品、专家、政策和事件综合关联' },
]

const attributes = [
  { entity: 'Expert', key: 'expert_id', core: 'name_zh, name_en, avatar, organization_name_zh, bio_zh, bio_en', dynamic: 'paper_count, citation_count, h_index', source: 'dwd_scholar' },
  { entity: 'Organization', key: 'org_id', core: 'name_zh, name_en, external_id, org_category, province, city, address', dynamic: 'listing_status, registered_capital_value, financial_metrics', source: 'dwd_org_reg_info / dwd_forg_base_info' },
  { entity: 'Paper', key: 'paper_id', core: 'doi, title_zh, title_en, publish_year, abstract_zh, abstract_en, keywords', dynamic: 'citation_count, is_open_access', source: 'dwd_zh_paper_detail / dwd_en_paper_detail' },
  { entity: 'Project', key: 'project_id', core: 'project_number, title, project_source, project_level, discipline_code, approval_time', dynamic: 'funded_amount, research_period', source: 'dwd_zh_project / dwd_en_project' },
  { entity: 'Patent', key: 'patent_id', core: 'publication_number, application_number, country_code, application_date, ipc_main, cpc_main', dynamic: 'legal_status, cited_by_nums, anticipated_expiration', source: 'dwd_patent' },
  { entity: 'Report', key: 'report_id', core: 'title_zh, title_en, authors_raw, organization_raw, abstract_zh, keywords_zh', dynamic: 'publication_date, preparation_time', source: 'dwd_zh_report / dwd_en_report' },
  { entity: 'Policy', key: 'policy_id', core: 'title, content, url, issueno, pubtime, region, keywords, publish_department', dynamic: '按政策源更新', source: 'dws_zck_policy / dwd_zck_intl_policy' },
  { entity: 'Event', key: 'event_id', core: 'event_type, title, event_time, summary, source_url, subject', dynamic: 'event_heat, impact_score', source: 'dwd_industry_chain_news_info / dwd_org_important_news_info' },
  { entity: 'IndustryChainNode', key: 'chain_code + node_id', core: 'node_name, node_type, level, parent_id, node_stage', dynamic: 'chain_score', source: 'dwd_industry_chain_info' },
  { entity: 'Product', key: 'product_id / 标准名', core: 'product_name, product_seq, company_name, credit_code', dynamic: '所属节点和企业映射', source: 'dwd_org_industry_chain_prod_dtl' },
  { entity: 'ResearchField', key: 'field_id / discipline_code', core: 'standard_name, alias, field_type, parent_field', dynamic: '别名与上下位字典', source: 'dim_research_field / dim_discipline_code' },
]

// 版本记录（已隐藏）
// const schemaVersions = [
//   { version: 'v1.8', status: '当前版本', time: '2026-07-12 22:10', entities: '14 个标准实体', relations: '42 标准 / 9 推理', change: '统一候选层字段；新增 Event 类型；调整 3 项关系约束', publisher: '张建图' },
//   { version: 'v1.7', status: '历史版本', time: '2026-06-28 18:30', entities: '13 个标准实体', relations: '39 标准 / 8 推理', change: '增加 Project / Patent 字段映射与对齐规则', publisher: '张建图' },
//   { version: 'v1.6', status: '历史版本', time: '2026-06-10 20:06', entities: '10 个标准实体', relations: '31 标准 / 6 推理', change: '建立专家、机构、论文与项目的基础 Schema', publisher: '张建图' },
// ]

const normalizedKeyword = computed(() => keyword.value.trim().toLowerCase())
const matches = (row: unknown) => !normalizedKeyword.value || Object.values(row as Record<string, unknown>).join(' ').toLowerCase().includes(normalizedKeyword.value)
const filteredEntities = computed(() => entities.filter(matches))
const filteredFacts = computed(() => factRelations.filter(matches))
const filteredInference = computed(() => inferenceRelations.filter(matches))
const filteredAttributes = computed(() => attributes.filter(matches))
</script>

<template>
  <main class="schema-page">
    <section class="schema-summary" aria-label="Schema 概览">
      <article><span>标准实体</span><strong>14</strong><em>专家、机构、论文等</em></article>
      <article><span>标准事实关系</span><strong>42</strong><em>专家、机构、成果等</em></article>
      <article><span>业务推理关系</span><strong>9</strong><em>均基于事实关系计算</em></article>
      <!-- <article><span>当前 Schema 版本</span><strong>v1.8</strong><em>已发布 · 2026-07-12</em></article> -->
    </section>

    <section class="schema-shell">
      <nav class="schema-tabs"><button v-for="tab in tabs" :key="tab" type="button" :class="{ active: activeTab === tab }" @click="activeTab=tab;keyword=''">{{ tab }}</button></nav>
      <div class="schema-toolbar"><div><strong>{{ activeTab }}</strong><span v-if="activeTab === '属性定义'">枚举字典作为属性约束统一维护</span></div><label><span>⌕</span><input v-model="keyword" :placeholder="`搜索${activeTab}`" /></label></div>
      <!-- <p v-if="schemaVersionMessage" class="schema-version-message">{{ schemaVersionMessage }}</p> -->

      <div v-if="activeTab === '标准实体'" class="schema-table-wrap"><table><thead><tr><th>实体中文名</th><th>Schema 名称</th><th>主键 / 唯一标识</th><th>主要来源表组</th><th>建模说明</th></tr></thead><tbody><tr v-for="row in filteredEntities" :key="row.name"><td><b>{{ row.label }}</b></td><td><code>{{ row.name }}</code></td><td>{{ row.key }}</td><td>{{ row.source }}</td><td>{{ row.description }}</td></tr></tbody></table></div>

      <div v-else-if="activeTab === '事实关系'" class="schema-table-wrap"><table><thead><tr><th>关系中文名</th><th>关系英文名</th><th>起点</th><th>终点</th><th>生成依据</th></tr></thead><tbody><tr v-for="row in filteredFacts" :key="row.name"><td><b>{{ row.label }}</b></td><td><code>{{ row.name }}</code></td><td>{{ row.source }}</td><td>{{ row.target }}</td><td>{{ row.basis }}</td></tr></tbody></table></div>

      <div v-else-if="activeTab === '推理关系'" class="schema-table-wrap"><table><thead><tr><th>推理关系</th><th>Schema 名称</th><th>起点</th><th>终点</th><th>生成依据</th></tr></thead><tbody><tr v-for="row in filteredInference" :key="row.name"><td><b>{{ row.label }}</b></td><td><code>{{ row.name }}</code></td><td>{{ row.source }}</td><td>{{ row.target }}</td><td>{{ row.basis }}</td></tr></tbody></table></div>

      <div v-else-if="activeTab === '属性定义'" class="schema-table-wrap"><table><thead><tr><th>实体</th><th>主键</th><th>核心属性</th><th>动态属性 / 补充</th><th>主要来源</th></tr></thead><tbody><tr v-for="row in filteredAttributes" :key="row.entity"><td><code>{{ row.entity }}</code></td><td><b>{{ row.key }}</b></td><td class="mono-list">{{ row.core }}</td><td>{{ row.dynamic }}</td><td>{{ row.source }}</td></tr></tbody></table></div>

      <!-- 版本记录（已隐藏）
      <div v-else class="schema-table-wrap schema-version-table"><table><thead><tr><th>版本</th><th>状态</th><th>发布时间</th><th>实体范围</th><th>关系范围</th><th>变更内容</th><th>发布人</th><th>操作</th></tr></thead><tbody><tr v-for="row in schemaVersions" :key="row.version"><td><code>{{ row.version }}</code></td><td><span :class="row.status === '当前版本' ? 'core' : 'support'">{{ row.status }}</span></td><td>{{ row.time }}</td><td>{{ row.entities }}</td><td>{{ row.relations }}</td><td>{{ row.change }}</td><td>{{ row.publisher }}</td><td><div class="schema-version-actions"><button type="button" @click="schemaVersionMessage = `已打开 ${row.version} 的完整变更清单。`">变更详情</button><button v-if="row.status !== '当前版本'" class="danger" type="button" @click="schemaVersionMessage = `已创建回退至 ${row.version} 的申请，通过影响分析与审批后才会执行。`">申请回退</button></div></td></tr></tbody></table></div>
      -->
    </section>
  </main>
</template>

<style scoped>
.schema-page{display:flex;height:100%;min-height:0;overflow:hidden;padding-bottom:2px;color:#142443;flex-direction:column}.schema-summary{display:grid;flex:0 0 auto;grid-template-columns:repeat(4,minmax(0,1fr));gap:11px;margin-bottom:12px}.schema-summary article{display:grid;gap:5px;padding:13px 15px;border:1px solid #bfd6fa;border-radius:8px;background:linear-gradient(145deg,#fff,#f2f8ff)}.schema-summary span{color:#687996;font-size:11px}.schema-summary strong{font-size:23px}.schema-summary em{color:#8191aa;font-size:10px;font-style:normal}.schema-flow{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));margin-bottom:12px;padding:12px;border:1px solid #c5d9f6;border-radius:8px;background:#fff}.schema-flow>div{position:relative;display:flex;align-items:center;gap:7px;min-width:0;padding:4px 15px 4px 5px}.schema-flow i{display:grid;flex:0 0 auto;place-items:center;width:23px;height:23px;border-radius:50%;background:#eaf2ff;color:#165dff;font-size:10px;font-style:normal}.schema-flow span{color:#40536f;font-size:10px;line-height:15px}.schema-flow b{position:absolute;right:2px;color:#9bb5d9}.schema-shell{display:flex;flex:1;min-height:0;overflow:hidden;border:1px solid #bcd4f7;border-radius:9px;background:#fff;box-shadow:0 10px 24px rgba(48,105,194,.08);flex-direction:column}.schema-tabs{display:flex;flex:0 0 auto;overflow:auto;padding:0 12px;border-bottom:1px solid #dce8f8}.schema-tabs button{padding:12px 15px;border:0;border-bottom:2px solid transparent;background:transparent;color:#566985;white-space:nowrap;cursor:pointer}.schema-tabs button.active{border-color:#165dff;color:#165dff;font-weight:600}.schema-toolbar{display:flex;flex:0 0 auto;align-items:center;justify-content:space-between;gap:14px;padding:10px 13px;border-bottom:1px solid #e3ebf6;background:#f8fbff}.schema-toolbar>div{display:flex;align-items:center;gap:10px}.schema-toolbar strong{font-size:13px}.schema-toolbar>div span{color:#7b8ba3;font-size:10px}.schema-toolbar label{display:flex;align-items:center;gap:6px;width:270px;padding:0 9px;border:1px solid #c7d8ef;border-radius:5px;background:#fff}.schema-toolbar input{width:100%;height:30px;border:0;outline:0;font-size:11px}.schema-table-wrap{flex:1;min-height:0;max-height:none;overflow:auto}.schema-table-wrap table,.trace-layout table{width:100%;border-collapse:collapse;font-size:11px}.schema-table-wrap th,.schema-table-wrap td,.trace-layout td{padding:11px 13px;border-bottom:1px solid #e5edf8;text-align:left;line-height:17px;vertical-align:top}.schema-table-wrap th{position:sticky;z-index:2;top:0;background:#f1f6fc;color:#5e6f88;white-space:nowrap}.schema-table-wrap td{color:#344763}.schema-table-wrap td:nth-child(5),.schema-table-wrap td:nth-child(6){max-width:330px}.schema-table-wrap code,.trace-layout code{padding:2px 6px;border-radius:4px;background:#edf4ff;color:#165dff;white-space:nowrap}.core,.support,.evidence,.auto,.review{display:inline-flex;padding:2px 7px;border-radius:999px;background:#e9f8ef;color:#067647;font-size:9px;white-space:nowrap}.support{background:#f0f2f5;color:#5e6b7e}.evidence{background:#f0edff;color:#6941c6}.auto{white-space:normal}.review{background:#fff3df;color:#b54708;white-space:normal}.mono-list{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:10px}.arrow{margin:0 5px;color:#8ba2c2}.candidate-layout{display:grid;flex:1;min-height:0;grid-template-columns:minmax(0,1fr) 245px}.candidate-layout>.schema-table-wrap{grid-column:1}.candidate-note{grid-column:1/-1;padding:10px 13px;border-bottom:1px solid #dce8f8;background:#f3f8ff}.candidate-note strong{font-size:12px}.candidate-note p{margin:3px 0 0;color:#657690;font-size:10px}.mention-fields{grid-column:2;grid-row:2;padding:13px;border-left:1px solid #e0e9f5;background:#fafcff}.mention-fields strong{display:block;margin-bottom:10px;font-size:12px}.mention-fields span{display:inline-flex;margin:0 5px 6px 0;padding:3px 6px;border-radius:4px;background:#edf4ff;color:#315b95;font:9px ui-monospace,SFMono-Regular,Menlo,monospace}.trace-layout{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding:12px;background:#f8fbff}.trace-layout section{overflow:hidden;border:1px solid #d5e3f5;border-radius:7px;background:#fff}.trace-layout header{display:flex;align-items:flex-start;justify-content:space-between;padding:13px;border-bottom:1px solid #e3ebf6}.trace-layout h2{margin:0;font-size:13px}.trace-layout p{margin:3px 0 0;color:#7b899e;font-size:10px}.trace-layout header>span{color:#165dff;font-size:10px}.trace-layout table{display:block;max-height:390px;overflow:auto}.trace-layout tbody,.trace-layout tr{display:table;width:100%;table-layout:fixed}.trace-layout td:first-child{width:160px}@media(max-width:1250px){.schema-summary{grid-template-columns:repeat(3,1fr)}.schema-flow{grid-template-columns:repeat(4,1fr)}.schema-flow b{display:none}}@media(max-width:900px){.schema-summary{grid-template-columns:repeat(2,1fr)}.trace-layout{grid-template-columns:1fr}.candidate-layout{display:block}.mention-fields{border-top:1px solid #e0e9f5;border-left:0}}

/* Layout refinements for wide management screens. */
.schema-page{box-sizing:border-box;padding:2px 2px 18px}
.schema-summary article{position:relative;min-height:92px;padding:15px 17px;overflow:hidden}
.schema-summary article::after{position:absolute;right:-15px;bottom:-28px;width:72px;height:72px;border-radius:50%;background:rgba(22,93,255,.055);content:""}
.schema-summary span{font-size:12px}.schema-summary strong{font-size:26px;line-height:31px}.schema-summary em{font-size:11px}

.schema-flow{display:block;margin-bottom:14px;padding:0;border-color:#bcd4f7;background:linear-gradient(180deg,#fff,#f6faff)}
.schema-flow>header{display:flex;align-items:center;gap:12px;padding:10px 15px;border-bottom:1px solid #dce8f8}
.schema-flow>header strong{color:#243b5d;font-size:13px}
.schema-flow>header span{color:#7a8aa3;font-size:11px}
.schema-flow ol{display:flex;align-items:stretch;margin:0;padding:12px 14px;list-style:none}
.schema-flow li{position:relative;flex:1;display:flex;align-items:center;gap:9px;min-width:0;padding:8px 26px 8px 10px;border:1px solid #d5e4f7;border-right:0;background:#fff}
.schema-flow li:first-child{border-radius:6px 0 0 6px}
.schema-flow li:last-child{border-right:1px solid #d5e4f7;border-radius:0 6px 6px 0}
.schema-flow li:not(:last-child)::after{position:absolute;z-index:2;right:-8px;width:15px;height:15px;border-top:1px solid #d5e4f7;border-right:1px solid #d5e4f7;background:#fff;content:"";transform:rotate(45deg)}
.schema-flow li i{position:relative;z-index:3;display:grid;flex:0 0 auto;place-items:center;width:25px;height:25px;border-radius:50%;background:#e9f2ff;color:#165dff;font-size:11px;font-style:normal;font-weight:700}
.schema-flow li:nth-child(4) i,.schema-flow li:nth-child(5) i{background:#e9f8ef;color:#067647}
.schema-flow li:nth-child(6) i,.schema-flow li:nth-child(7) i{background:#f1edff;color:#6941c6}
.schema-flow li span{position:relative;z-index:3;color:#40536f;font-size:11px;line-height:16px}

.schema-shell{min-height:0}
.schema-tabs{min-height:45px;background:#fff}
.schema-tabs button{padding:13px 18px;font-size:12px}
.schema-toolbar{min-height:48px;padding:9px 16px}
.schema-toolbar strong{font-size:15px}
.schema-toolbar>div span{font-size:11px}

.trace-layout{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;min-height:435px;padding:16px;background:#f7faff}
.trace-card{display:flex;min-width:0;overflow:hidden;border:1px solid #cfdef2;border-radius:9px;background:#fff;box-shadow:0 6px 16px rgba(48,105,194,.06);flex-direction:column}
.trace-card>header{display:flex;align-items:center;justify-content:space-between;min-height:68px;padding:13px 15px;border-bottom:1px solid #e0e9f5;background:linear-gradient(90deg,#eef5ff,#fff 62%)}
.trace-card>header>div{display:flex;align-items:center;gap:10px}
.trace-card>header i{display:grid;place-items:center;width:31px;height:31px;border-radius:8px;background:#165dff;color:#fff;font-size:11px;font-style:normal;font-weight:700}
.trace-card>header span{display:block}
.trace-card h2{margin:0;color:#20324e;font-size:14px}
.trace-card p{margin:3px 0 0;color:#74849b;font-size:10px}
.trace-card>header b{padding:4px 8px;border-radius:999px;background:#eaf2ff;color:#165dff;font-size:10px;font-weight:500;white-space:nowrap}
.trace-card dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-content:start;margin:0;padding:10px}
.trace-card dl>div{min-width:0;padding:10px 11px;border-right:1px solid #e8eef7;border-bottom:1px solid #e8eef7}
.trace-card dl>div:nth-child(2n){border-right:0}
.trace-card dt{margin-bottom:5px}
.trace-card dd{margin:0;color:#53647d;font-size:10px;line-height:16px}
.trace-card code{display:inline-flex;max-width:100%;padding:3px 7px;border-radius:4px;background:#edf4ff;color:#165dff;font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.trace-layout>aside{grid-column:1/-1;display:flex;align-items:center;gap:22px;min-height:48px;padding:10px 14px;border:1px solid #d4e1f2;border-radius:7px;background:#fff}
.trace-layout>aside strong{color:#263b5a;font-size:11px;white-space:nowrap}
.trace-layout>aside span{display:flex;align-items:flex-start;gap:7px;color:#64758d;font-size:10px;line-height:16px}
.trace-layout>aside i{flex:0 0 auto;width:6px;height:6px;margin-top:5px;border-radius:50%;background:#165dff}

@media(max-width:1500px){.schema-flow li{padding-right:18px}.schema-flow li span{font-size:10px}.trace-card dl{grid-template-columns:1fr}.trace-card dl>div{border-right:0}}
@media(max-width:1100px){.schema-flow ol{display:grid;grid-template-columns:repeat(2,1fr);gap:7px}.schema-flow li,.schema-flow li:last-child{border:1px solid #d5e4f7;border-radius:6px}.schema-flow li::after{display:none}.trace-layout{grid-template-columns:1fr}.trace-layout>aside{grid-column:1;align-items:flex-start;flex-direction:column;gap:7px}.trace-card dl{grid-template-columns:repeat(2,1fr)}.trace-card dl>div{border-right:1px solid #e8eef7}.trace-card dl>div:nth-child(2n){border-right:0}}
.schema-summary{grid-template-columns:repeat(3,minmax(0,1fr))}
.schema-version-message{margin:0;padding:9px 13px;border-bottom:1px solid #b7d0f5;background:#eef5ff;color:#344f7a;font-size:11px}
.schema-version-table{max-height:470px}.schema-version-table td:nth-child(6){min-width:280px}.schema-version-actions{display:flex;gap:6px}.schema-version-actions button{padding:3px 7px;border:1px solid #bdd0ea;border-radius:4px;background:#fff;color:#165dff;font-size:9px;white-space:nowrap;cursor:pointer}.schema-version-actions button.danger{border-color:#f6b9b4;color:#b42318}
@media(max-width:1500px){.schema-summary{grid-template-columns:repeat(3,1fr)}}
</style>
