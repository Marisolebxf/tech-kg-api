// 科技知识图谱 Neo4j 5.x 建表和样例数据导入完整脚本
// 适用环境：Neo4j Desktop 2 + Neo4j 5.x
//
// 使用方式：
// 1. 在 Neo4j Desktop 2 中启动一个 Neo4j 5.x 数据库。
// 2. 打开 Query。
// 3. 将本文件内容整体粘贴执行，或用 cypher-shell 执行整文件。
//
// 说明：
// 1. 这份脚本包含“唯一约束 + 常用索引 + 可直接查询的样例数据”。
// 2. Neo4j 没有 CREATE TAG / CREATE EDGE 语法，Label 和 Relationship Type 会在 CREATE / MERGE 时自动出现。
// 3. 这是可运行示例，字段命名与前面的 schema 文件保持一致，便于后续替换成真实数据。
//
// 如需清空库重跑，请手动先执行：
// MATCH (n) DETACH DELETE n;
// 这条语句是破坏性的，因此默认不放到正式脚本里。


// -----------------------------------------------------------------------------
// 1. 唯一约束
// -----------------------------------------------------------------------------

CREATE CONSTRAINT scholar_id_unique IF NOT EXISTS
FOR (n:Scholar) REQUIRE n.scholar_id IS UNIQUE;

CREATE CONSTRAINT organization_id_unique IF NOT EXISTS
FOR (n:Organization) REQUIRE n.org_id IS UNIQUE;

CREATE CONSTRAINT department_id_unique IF NOT EXISTS
FOR (n:Department) REQUIRE n.dept_id IS UNIQUE;

CREATE CONSTRAINT paper_id_unique IF NOT EXISTS
FOR (n:Paper) REQUIRE n.paper_id IS UNIQUE;

CREATE CONSTRAINT paper_doi_unique IF NOT EXISTS
FOR (n:Paper) REQUIRE n.doi IS UNIQUE;

CREATE CONSTRAINT venue_id_unique IF NOT EXISTS
FOR (n:Venue) REQUIRE n.venue_id IS UNIQUE;

CREATE CONSTRAINT patent_id_unique IF NOT EXISTS
FOR (n:Patent) REQUIRE n.patent_id IS UNIQUE;

CREATE CONSTRAINT patent_no_unique IF NOT EXISTS
FOR (n:Patent) REQUIRE n.patent_no IS UNIQUE;

CREATE CONSTRAINT patent_application_no_unique IF NOT EXISTS
FOR (n:Patent) REQUIRE n.application_no IS UNIQUE;

CREATE CONSTRAINT project_id_unique IF NOT EXISTS
FOR (n:Project) REQUIRE n.project_id IS UNIQUE;

CREATE CONSTRAINT project_no_unique IF NOT EXISTS
FOR (n:Project) REQUIRE n.project_no IS UNIQUE;

CREATE CONSTRAINT enterprise_id_unique IF NOT EXISTS
FOR (n:Enterprise) REQUIRE n.enterprise_id IS UNIQUE;

CREATE CONSTRAINT enterprise_uscc_unique IF NOT EXISTS
FOR (n:Enterprise) REQUIRE n.uscc IS UNIQUE;

CREATE CONSTRAINT school_id_unique IF NOT EXISTS
FOR (n:School) REQUIRE n.school_id IS UNIQUE;

CREATE CONSTRAINT college_id_unique IF NOT EXISTS
FOR (n:College) REQUIRE n.college_id IS UNIQUE;

CREATE CONSTRAINT technology_id_unique IF NOT EXISTS
FOR (n:Technology) REQUIRE n.tech_id IS UNIQUE;

CREATE CONSTRAINT industry_segment_id_unique IF NOT EXISTS
FOR (n:IndustrySegment) REQUIRE n.segment_id IS UNIQUE;

CREATE CONSTRAINT team_id_unique IF NOT EXISTS
FOR (n:Team) REQUIRE n.team_id IS UNIQUE;

CREATE CONSTRAINT industry_event_id_unique IF NOT EXISTS
FOR (n:IndustryEvent) REQUIRE n.event_id IS UNIQUE;

CREATE CONSTRAINT capital_event_id_unique IF NOT EXISTS
FOR (n:CapitalEvent) REQUIRE n.capital_event_id IS UNIQUE;

CREATE CONSTRAINT award_id_unique IF NOT EXISTS
FOR (n:Award) REQUIRE n.award_id IS UNIQUE;

CREATE CONSTRAINT update_batch_id_unique IF NOT EXISTS
FOR (n:UpdateBatch) REQUIRE n.batch_id IS UNIQUE;

CREATE CONSTRAINT authorship_id_unique IF NOT EXISTS
FOR (n:Authorship) REQUIRE n.authorship_id IS UNIQUE;

CREATE CONSTRAINT inventorship_id_unique IF NOT EXISTS
FOR (n:Inventorship) REQUIRE n.inventorship_id IS UNIQUE;

CREATE CONSTRAINT project_participation_id_unique IF NOT EXISTS
FOR (n:ProjectParticipation) REQUIRE n.participation_id IS UNIQUE;

CREATE CONSTRAINT employment_id_unique IF NOT EXISTS
FOR (n:Employment) REQUIRE n.employment_id IS UNIQUE;

CREATE CONSTRAINT education_id_unique IF NOT EXISTS
FOR (n:Education) REQUIRE n.education_id IS UNIQUE;

CREATE CONSTRAINT enterprise_cooperation_id_unique IF NOT EXISTS
FOR (n:EnterpriseCooperation) REQUIRE n.coop_id IS UNIQUE;

CREATE CONSTRAINT inference_path_id_unique IF NOT EXISTS
FOR (n:InferencePath) REQUIRE n.path_id IS UNIQUE;

CREATE CONSTRAINT trend_report_id_unique IF NOT EXISTS
FOR (n:TrendReport) REQUIRE n.report_id IS UNIQUE;


// -----------------------------------------------------------------------------
// 2. 常用索引
// -----------------------------------------------------------------------------

CREATE TEXT INDEX scholar_name_idx IF NOT EXISTS
FOR (n:Scholar) ON (n.name);

CREATE TEXT INDEX paper_title_idx IF NOT EXISTS
FOR (n:Paper) ON (n.title);

CREATE RANGE INDEX paper_year_idx IF NOT EXISTS
FOR (n:Paper) ON (n.year);

CREATE TEXT INDEX enterprise_name_idx IF NOT EXISTS
FOR (n:Enterprise) ON (n.enterprise_name);

CREATE TEXT INDEX technology_name_idx IF NOT EXISTS
FOR (n:Technology) ON (n.tech_name);

CREATE TEXT INDEX industry_segment_name_idx IF NOT EXISTS
FOR (n:IndustrySegment) ON (n.segment_name);

CREATE RANGE INDEX industry_event_time_idx IF NOT EXISTS
FOR (n:IndustryEvent) ON (n.event_time);

CREATE RANGE INDEX direct_rel_confidence_idx IF NOT EXISTS
FOR ()-[r:DIRECT_REL]-() ON (r.confidence);

CREATE RANGE INDEX indirect_rel_strength_score_idx IF NOT EXISTS
FOR ()-[r:INDIRECT_REL]-() ON (r.strength_score);

CREATE TEXT INDEX expert_enterprise_rel_relation_type_idx IF NOT EXISTS
FOR ()-[r:EXPERT_ENTERPRISE_REL]-() ON (r.relation_type);


// -----------------------------------------------------------------------------
// 3. 样例基础节点
// -----------------------------------------------------------------------------

MERGE (batch:UpdateBatch {batch_id: 'BATCH-20260412-DEMO'})
SET batch.version_no = 'v1.0-demo',
    batch.source_name = 'manual_demo',
    batch.load_time = datetime('2026-04-12T10:00:00'),
    batch.change_type = 'INIT_LOAD',
    batch.operator_name = 'Codex';

MERGE (org1:Organization {org_id: 'ORG001'})
SET org1.org_name = '燕山大学',
    org1.org_type = '高校',
    org1.region = '河北秦皇岛',
    org1.uscc = '12130000401704445A',
    org1.updated_at = datetime('2026-04-12T10:00:00');

MERGE (org2:Organization {org_id: 'ORG002'})
SET org2.org_name = '清华大学',
    org2.org_type = '高校',
    org2.region = '北京',
    org2.uscc = '12100000400006157A',
    org2.updated_at = datetime('2026-04-12T10:00:00');

MERGE (dept1:Department {dept_id: 'DEPT001'})
SET dept1.dept_name = '计算机科学与技术学院',
    dept1.dept_type = '学院',
    dept1.org_id = 'ORG001',
    dept1.updated_at = datetime('2026-04-12T10:00:00');

MERGE (dept2:Department {dept_id: 'DEPT002'})
SET dept2.dept_name = '人工智能研究院',
    dept2.dept_type = '研究院',
    dept2.org_id = 'ORG002',
    dept2.updated_at = datetime('2026-04-12T10:00:00');

MERGE (school1:School {school_id: 'SCH001'})
SET school1.school_name = '燕山大学',
    school1.region = '河北秦皇岛',
    school1.school_type = '高校',
    school1.updated_at = datetime('2026-04-12T10:00:00');

MERGE (college1:College {college_id: 'COL001'})
SET college1.college_name = '计算机科学与技术学院',
    college1.discipline_group = '工学',
    college1.school_id = 'SCH001',
    college1.updated_at = datetime('2026-04-12T10:00:00');

MERGE (venue1:Venue {venue_id: 'VENUE001'})
SET venue1.venue_name = 'Journal of Knowledge Graph',
    venue1.venue_type = '期刊',
    venue1.ccf_level = 'B',
    venue1.sci_partition = '二区',
    venue1.issn = '1000-0001',
    venue1.updated_at = datetime('2026-04-12T10:00:00');

MERGE (paper1:Paper {paper_id: 'PAPER001'})
SET paper1.title = '科技知识图谱构建方法研究',
    paper1.doi = '10.1000/kg-001',
    paper1.publish_date = date('2024-06-01'),
    paper1.year = 2024,
    paper1.venue_id = 'VENUE001',
    paper1.journal_level = '核心期刊',
    paper1.citation_count = 56,
    paper1.keywords_text = '["知识图谱","图数据库","科研合作"]',
    paper1.updated_at = datetime('2026-04-12T10:00:00');

MERGE (paper2:Paper {paper_id: 'PAPER002'})
SET paper2.title = '学者关系推理与路径分析',
    paper2.doi = '10.1000/kg-002',
    paper2.publish_date = date('2025-03-15'),
    paper2.year = 2025,
    paper2.venue_id = 'VENUE001',
    paper2.journal_level = '核心期刊',
    paper2.citation_count = 24,
    paper2.keywords_text = '["关系推理","路径分析"]',
    paper2.updated_at = datetime('2026-04-12T10:00:00');

MERGE (patent1:Patent {patent_id: 'PAT001'})
SET patent1.patent_no = 'CN202410000001',
    patent1.application_no = 'CN202410000001.1',
    patent1.title = '一种科研知识图谱推理方法',
    patent1.apply_date = date('2024-02-01'),
    patent1.grant_date = date('2025-08-01'),
    patent1.ipc_cpc_text = '["G06F16/36","G06N5/02"]',
    patent1.legal_status = '授权',
    patent1.updated_at = datetime('2026-04-12T10:00:00');

MERGE (project1:Project {project_id: 'PROJ001'})
SET project1.project_no = 'NSFC-62400001',
    project1.project_name = '面向科技人才评估的知识图谱关键技术',
    project1.project_type = '国家自然科学基金',
    project1.start_date = date('2024-01-01'),
    project1.end_date = date('2027-12-31'),
    project1.funding = 800000.0,
    project1.project_status = '在研',
    project1.updated_at = datetime('2026-04-12T10:00:00');

MERGE (enterprise1:Enterprise {enterprise_id: 'ENT001'})
SET enterprise1.enterprise_name = '河北智图科技有限公司',
    enterprise1.uscc = '91130300MA12345678',
    enterprise1.industry = '人工智能',
    enterprise1.region = '河北秦皇岛',
    enterprise1.establish_date = date('2020-05-20'),
    enterprise1.listed_status = '未上市',
    enterprise1.specialized_tag_text = '["高新技术企业","专精特新"]',
    enterprise1.industry_rank_text = '区域前20',
    enterprise1.updated_at = datetime('2026-04-12T10:00:00');

MERGE (tech1:Technology {tech_id: 'TECH001'})
SET tech1.tech_name = '知识图谱推理',
    tech1.tech_direction = '语义计算',
    tech1.tech_level = '关键技术',
    tech1.keywords_text = '["图谱推理","规则推理","路径分析"]',
    tech1.updated_at = datetime('2026-04-12T10:00:00');

MERGE (tech2:Technology {tech_id: 'TECH002'})
SET tech2.tech_name = '科研画像分析',
    tech2.tech_direction = '人才评估',
    tech2.tech_level = '应用技术',
    tech2.keywords_text = '["人才画像","合作网络"]',
    tech2.updated_at = datetime('2026-04-12T10:00:00');

MERGE (seg1:IndustrySegment {segment_id: 'SEG001'})
SET seg1.segment_name = '基础算法',
    seg1.segment_level = 1,
    seg1.chain_position = '上游',
    seg1.parent_segment_id = '',
    seg1.updated_at = datetime('2026-04-12T10:00:00');

MERGE (seg2:IndustrySegment {segment_id: 'SEG002'})
SET seg2.segment_name = '科研智能应用',
    seg2.segment_level = 1,
    seg2.chain_position = '中游',
    seg2.parent_segment_id = '',
    seg2.updated_at = datetime('2026-04-12T10:00:00');

MERGE (team1:Team {team_id: 'TEAM001'})
SET team1.team_name = '科技情报与知识图谱团队',
    team1.team_type = '科研团队',
    team1.org_id = 'ORG001',
    team1.leader_id = 'SCH001',
    team1.updated_at = datetime('2026-04-12T10:00:00');

MERGE (event1:IndustryEvent {event_id: 'EVENT001'})
SET event1.event_name = '科研知识图谱平台中标事件',
    event1.event_type = '重大项目',
    event1.event_time = datetime('2025-09-01T09:00:00'),
    event1.segment_id = 'SEG002',
    event1.impact_score = 92.5,
    event1.top_n_rank = 1,
    event1.summary = '某省级科研知识图谱平台建设项目中标，推动产业链应用加速。',
    event1.updated_at = datetime('2026-04-12T10:00:00');

MERGE (capital1:CapitalEvent {capital_event_id: 'CAP001'})
SET capital1.investor_name = '某产业基金',
    capital1.amount = 5000000.0,
    capital1.event_time = datetime('2025-05-20T10:30:00'),
    capital1.round_name = 'A轮',
    capital1.updated_at = datetime('2026-04-12T10:00:00');

MERGE (award1:Award {award_id: 'AWD001'})
SET award1.award_name = '省科技进步奖',
    award1.award_level = '二等奖',
    award1.award_year = 2025,
    award1.updated_at = datetime('2026-04-12T10:00:00');

MERGE (scholar1:Scholar {scholar_id: 'SCH001'})
SET scholar1.name = '张三',
    scholar1.alias_text = '["Zhang San"]',
    scholar1.gender = '男',
    scholar1.title = '教授',
    scholar1.research_fields_text = '["知识图谱","语义检索"]',
    scholar1.discipline_text = '["计算机科学与技术"]',
    scholar1.h_index = 42.0,
    scholar1.citation_count = 1200,
    scholar1.org_name_std = '燕山大学',
    scholar1.updated_at = datetime('2026-04-12T10:00:00');

MERGE (scholar2:Scholar {scholar_id: 'SCH002'})
SET scholar2.name = '李四',
    scholar2.alias_text = '["Li Si"]',
    scholar2.gender = '男',
    scholar2.title = '副教授',
    scholar2.research_fields_text = '["知识推理","科研评价"]',
    scholar2.discipline_text = '["软件工程"]',
    scholar2.h_index = 31.0,
    scholar2.citation_count = 860,
    scholar2.org_name_std = '燕山大学',
    scholar2.updated_at = datetime('2026-04-12T10:00:00');

MERGE (scholar3:Scholar {scholar_id: 'SCH003'})
SET scholar3.name = '王五',
    scholar3.alias_text = '["Wang Wu"]',
    scholar3.gender = '女',
    scholar3.title = '研究员',
    scholar3.research_fields_text = '["产业链分析","技术路线"]',
    scholar3.discipline_text = '["人工智能"]',
    scholar3.h_index = 28.0,
    scholar3.citation_count = 630,
    scholar3.org_name_std = '清华大学',
    scholar3.updated_at = datetime('2026-04-12T10:00:00');


// -----------------------------------------------------------------------------
// 4. 样例事实节点
// -----------------------------------------------------------------------------

MERGE (auth1:Authorship {authorship_id: 'AUTH001'})
SET auth1.author_order = 1,
    auth1.is_corresponding = true,
    auth1.org_name_raw = '燕山大学',
    auth1.confidence = 0.99,
    auth1.updated_at = datetime('2026-04-12T10:00:00');

MERGE (auth2:Authorship {authorship_id: 'AUTH002'})
SET auth2.author_order = 2,
    auth2.is_corresponding = false,
    auth2.org_name_raw = '燕山大学',
    auth2.confidence = 0.98,
    auth2.updated_at = datetime('2026-04-12T10:00:00');

MERGE (inv1:Inventorship {inventorship_id: 'INV001'})
SET inv1.inventor_order = 1,
    inv1.applicant_name_raw = '燕山大学',
    inv1.confidence = 0.97,
    inv1.updated_at = datetime('2026-04-12T10:00:00');

MERGE (inv2:Inventorship {inventorship_id: 'INV002'})
SET inv2.inventor_order = 2,
    inv2.applicant_name_raw = '燕山大学',
    inv2.confidence = 0.95,
    inv2.updated_at = datetime('2026-04-12T10:00:00');

MERGE (pp1:ProjectParticipation {participation_id: 'PP001'})
SET pp1.role = '负责人',
    pp1.responsibility = '总体设计与算法研发',
    pp1.start_date = date('2024-01-01'),
    pp1.end_date = date('2027-12-31'),
    pp1.confidence = 0.99,
    pp1.updated_at = datetime('2026-04-12T10:00:00');

MERGE (pp2:ProjectParticipation {participation_id: 'PP002'})
SET pp2.role = '骨干成员',
    pp2.responsibility = '图数据库建模与实现',
    pp2.start_date = date('2024-01-01'),
    pp2.end_date = date('2027-12-31'),
    pp2.confidence = 0.98,
    pp2.updated_at = datetime('2026-04-12T10:00:00');

MERGE (emp1:Employment {employment_id: 'EMP001'})
SET emp1.position_name = '教师',
    emp1.title_level = '教授',
    emp1.start_date = date('2020-01-01'),
    emp1.end_date = date('2026-12-31'),
    emp1.employment_status = '在职',
    emp1.source_name = '人事系统',
    emp1.updated_at = datetime('2026-04-12T10:00:00');

MERGE (emp2:Employment {employment_id: 'EMP002'})
SET emp2.position_name = '教师',
    emp2.title_level = '副教授',
    emp2.start_date = date('2021-01-01'),
    emp2.end_date = date('2026-12-31'),
    emp2.employment_status = '在职',
    emp2.source_name = '人事系统',
    emp2.updated_at = datetime('2026-04-12T10:00:00');

MERGE (emp3:Employment {employment_id: 'EMP003'})
SET emp3.position_name = '研究员',
    emp3.title_level = '研究员',
    emp3.start_date = date('2022-01-01'),
    emp3.end_date = date('2026-12-31'),
    emp3.employment_status = '在职',
    emp3.source_name = '人事系统',
    emp3.updated_at = datetime('2026-04-12T10:00:00');

MERGE (edu1:Education {education_id: 'EDU001'})
SET edu1.major = '计算机科学与技术',
    edu1.degree = '博士',
    edu1.education_level = '博士研究生',
    edu1.start_date = date('2012-09-01'),
    edu1.end_date = date('2016-06-30'),
    edu1.updated_at = datetime('2026-04-12T10:00:00');

MERGE (edu2:Education {education_id: 'EDU002'})
SET edu2.major = '软件工程',
    edu2.degree = '硕士',
    edu2.education_level = '硕士研究生',
    edu2.start_date = date('2013-09-01'),
    edu2.end_date = date('2016-06-30'),
    edu2.updated_at = datetime('2026-04-12T10:00:00');

MERGE (edu3:Education {education_id: 'EDU003'})
SET edu3.major = '人工智能',
    edu3.degree = '博士',
    edu3.education_level = '博士研究生',
    edu3.start_date = date('2014-09-01'),
    edu3.end_date = date('2018-06-30'),
    edu3.updated_at = datetime('2026-04-12T10:00:00');

MERGE (coop1:EnterpriseCooperation {coop_id: 'COOP001'})
SET coop1.coop_type = '研发合作',
    coop1.role = '首席顾问',
    coop1.tech_field_text = '["知识图谱推理","科研评价"]',
    coop1.start_date = date('2024-03-01'),
    coop1.end_date = date('2026-12-31'),
    coop1.coop_mode = '联合研发',
    coop1.risk_tag_text = '["低风险"]',
    coop1.value_score = 88.0,
    coop1.updated_at = datetime('2026-04-12T10:00:00');

MERGE (path1:InferencePath {path_id: 'PATH001'})
SET path1.path_length = 2,
    path1.path_signature = 'SCH001->SCH002->SCH003',
    path1.path_nodes_text = '["SCH001","SCH002","SCH003"]',
    path1.path_edges_text = '["DIRECT_REL","DIRECT_REL"]',
    path1.strength_score = 78.5,
    path1.relation_label = '潜在合作',
    path1.rule_version = 'rule_v1',
    path1.generated_at = datetime('2026-04-12T10:00:00');

MERGE (report1:TrendReport {report_id: 'TR001'})
SET report1.analysis_time = datetime('2026-04-12T10:00:00'),
    report1.trend_direction = '上升',
    report1.risk_point = '市场竞争加剧',
    report1.opportunity_point = '科研数字化建设需求持续增长',
    report1.report_text = '科研知识图谱平台建设进入加速期，知识推理与科研评价场景需求明显上升。',
    report1.updated_at = datetime('2026-04-12T10:00:00');


// -----------------------------------------------------------------------------
// 5. 事实关系
// -----------------------------------------------------------------------------

MATCH (scholar1:Scholar {scholar_id: 'SCH001'}), (auth1:Authorship {authorship_id: 'AUTH001'})
MERGE (scholar1)-[r1:HAS_AUTHORSHIP]->(auth1)
SET r1.source_name = 'manual_demo', r1.batch_id = 'BATCH-20260412-DEMO';

MATCH (scholar2:Scholar {scholar_id: 'SCH002'}), (auth2:Authorship {authorship_id: 'AUTH002'})
MERGE (scholar2)-[r2:HAS_AUTHORSHIP]->(auth2)
SET r2.source_name = 'manual_demo', r2.batch_id = 'BATCH-20260412-DEMO';

MATCH (auth1:Authorship {authorship_id: 'AUTH001'}), (paper1:Paper {paper_id: 'PAPER001'})
MERGE (auth1)-[r3:AUTHOR_OF]->(paper1)
SET r3.source_name = 'manual_demo', r3.batch_id = 'BATCH-20260412-DEMO';

MATCH (auth2:Authorship {authorship_id: 'AUTH002'}), (paper1:Paper {paper_id: 'PAPER001'})
MERGE (auth2)-[r4:AUTHOR_OF]->(paper1)
SET r4.source_name = 'manual_demo', r4.batch_id = 'BATCH-20260412-DEMO';

MATCH (paper1:Paper {paper_id: 'PAPER001'}), (venue1:Venue {venue_id: 'VENUE001'})
MERGE (paper1)-[r5:PUBLISHED_IN]->(venue1)
SET r5.source_name = 'manual_demo', r5.batch_id = 'BATCH-20260412-DEMO';

MATCH (scholar1:Scholar {scholar_id: 'SCH001'}), (inv1:Inventorship {inventorship_id: 'INV001'})
MERGE (scholar1)-[r6:HAS_INVENTORSHIP]->(inv1)
SET r6.source_name = 'manual_demo', r6.batch_id = 'BATCH-20260412-DEMO';

MATCH (scholar2:Scholar {scholar_id: 'SCH002'}), (inv2:Inventorship {inventorship_id: 'INV002'})
MERGE (scholar2)-[r7:HAS_INVENTORSHIP]->(inv2)
SET r7.source_name = 'manual_demo', r7.batch_id = 'BATCH-20260412-DEMO';

MATCH (inv1:Inventorship {inventorship_id: 'INV001'}), (patent1:Patent {patent_id: 'PAT001'})
MERGE (inv1)-[r8:INVENTOR_OF]->(patent1)
SET r8.source_name = 'manual_demo', r8.batch_id = 'BATCH-20260412-DEMO';

MATCH (inv2:Inventorship {inventorship_id: 'INV002'}), (patent1:Patent {patent_id: 'PAT001'})
MERGE (inv2)-[r9:INVENTOR_OF]->(patent1)
SET r9.source_name = 'manual_demo', r9.batch_id = 'BATCH-20260412-DEMO';

MATCH (scholar1:Scholar {scholar_id: 'SCH001'}), (pp1:ProjectParticipation {participation_id: 'PP001'})
MERGE (scholar1)-[r10:HAS_PARTICIPATION]->(pp1)
SET r10.source_name = 'manual_demo', r10.batch_id = 'BATCH-20260412-DEMO';

MATCH (scholar2:Scholar {scholar_id: 'SCH002'}), (pp2:ProjectParticipation {participation_id: 'PP002'})
MERGE (scholar2)-[r11:HAS_PARTICIPATION]->(pp2)
SET r11.source_name = 'manual_demo', r11.batch_id = 'BATCH-20260412-DEMO';

MATCH (pp1:ProjectParticipation {participation_id: 'PP001'}), (project1:Project {project_id: 'PROJ001'})
MERGE (pp1)-[r12:PARTICIPATES_IN]->(project1)
SET r12.source_name = 'manual_demo', r12.batch_id = 'BATCH-20260412-DEMO';

MATCH (pp2:ProjectParticipation {participation_id: 'PP002'}), (project1:Project {project_id: 'PROJ001'})
MERGE (pp2)-[r13:PARTICIPATES_IN]->(project1)
SET r13.source_name = 'manual_demo', r13.batch_id = 'BATCH-20260412-DEMO';

MATCH (scholar1:Scholar {scholar_id: 'SCH001'}), (emp1:Employment {employment_id: 'EMP001'})
MERGE (scholar1)-[r14:HAS_EMPLOYMENT]->(emp1)
SET r14.source_name = 'manual_demo', r14.batch_id = 'BATCH-20260412-DEMO';

MATCH (scholar2:Scholar {scholar_id: 'SCH002'}), (emp2:Employment {employment_id: 'EMP002'})
MERGE (scholar2)-[r15:HAS_EMPLOYMENT]->(emp2)
SET r15.source_name = 'manual_demo', r15.batch_id = 'BATCH-20260412-DEMO';

MATCH (scholar3:Scholar {scholar_id: 'SCH003'}), (emp3:Employment {employment_id: 'EMP003'})
MERGE (scholar3)-[r16:HAS_EMPLOYMENT]->(emp3)
SET r16.source_name = 'manual_demo', r16.batch_id = 'BATCH-20260412-DEMO';

MATCH (emp1:Employment {employment_id: 'EMP001'}), (org1:Organization {org_id: 'ORG001'})
MERGE (emp1)-[r17:EMPLOYED_BY]->(org1)
SET r17.source_name = 'manual_demo', r17.batch_id = 'BATCH-20260412-DEMO';

MATCH (emp2:Employment {employment_id: 'EMP002'}), (org1:Organization {org_id: 'ORG001'})
MERGE (emp2)-[r18:EMPLOYED_BY]->(org1)
SET r18.source_name = 'manual_demo', r18.batch_id = 'BATCH-20260412-DEMO';

MATCH (emp3:Employment {employment_id: 'EMP003'}), (org2:Organization {org_id: 'ORG002'})
MERGE (emp3)-[r19:EMPLOYED_BY]->(org2)
SET r19.source_name = 'manual_demo', r19.batch_id = 'BATCH-20260412-DEMO';

MATCH (emp1:Employment {employment_id: 'EMP001'}), (dept1:Department {dept_id: 'DEPT001'})
MERGE (emp1)-[r20:IN_DEPARTMENT]->(dept1)
SET r20.source_name = 'manual_demo', r20.batch_id = 'BATCH-20260412-DEMO';

MATCH (emp2:Employment {employment_id: 'EMP002'}), (dept1:Department {dept_id: 'DEPT001'})
MERGE (emp2)-[r21:IN_DEPARTMENT]->(dept1)
SET r21.source_name = 'manual_demo', r21.batch_id = 'BATCH-20260412-DEMO';

MATCH (scholar1:Scholar {scholar_id: 'SCH001'}), (edu1:Education {education_id: 'EDU001'})
MERGE (scholar1)-[r22:HAS_EDUCATION]->(edu1)
SET r22.source_name = 'manual_demo', r22.batch_id = 'BATCH-20260412-DEMO';

MATCH (scholar2:Scholar {scholar_id: 'SCH002'}), (edu2:Education {education_id: 'EDU002'})
MERGE (scholar2)-[r23:HAS_EDUCATION]->(edu2)
SET r23.source_name = 'manual_demo', r23.batch_id = 'BATCH-20260412-DEMO';

MATCH (scholar3:Scholar {scholar_id: 'SCH003'}), (edu3:Education {education_id: 'EDU003'})
MERGE (scholar3)-[r24:HAS_EDUCATION]->(edu3)
SET r24.source_name = 'manual_demo', r24.batch_id = 'BATCH-20260412-DEMO';

MATCH (edu1:Education {education_id: 'EDU001'}), (school1:School {school_id: 'SCH001'})
MERGE (edu1)-[r25:STUDIED_AT]->(school1)
SET r25.source_name = 'manual_demo', r25.batch_id = 'BATCH-20260412-DEMO';

MATCH (edu2:Education {education_id: 'EDU002'}), (school1:School {school_id: 'SCH001'})
MERGE (edu2)-[r26:STUDIED_AT]->(school1)
SET r26.source_name = 'manual_demo', r26.batch_id = 'BATCH-20260412-DEMO';

MATCH (edu1:Education {education_id: 'EDU001'}), (college1:College {college_id: 'COL001'})
MERGE (edu1)-[r27:IN_COLLEGE]->(college1)
SET r27.source_name = 'manual_demo', r27.batch_id = 'BATCH-20260412-DEMO';

MATCH (edu2:Education {education_id: 'EDU002'}), (college1:College {college_id: 'COL001'})
MERGE (edu2)-[r28:IN_COLLEGE]->(college1)
SET r28.source_name = 'manual_demo', r28.batch_id = 'BATCH-20260412-DEMO';

MATCH (scholar1:Scholar {scholar_id: 'SCH001'}), (coop1:EnterpriseCooperation {coop_id: 'COOP001'})
MERGE (scholar1)-[r29:HAS_ENTERPRISE_COOP]->(coop1)
SET r29.source_name = 'manual_demo', r29.batch_id = 'BATCH-20260412-DEMO';

MATCH (coop1:EnterpriseCooperation {coop_id: 'COOP001'}), (enterprise1:Enterprise {enterprise_id: 'ENT001'})
MERGE (coop1)-[r30:COOP_WITH_ENTERPRISE]->(enterprise1)
SET r30.source_name = 'manual_demo', r30.batch_id = 'BATCH-20260412-DEMO';

MATCH (coop1:EnterpriseCooperation {coop_id: 'COOP001'}), (tech1:Technology {tech_id: 'TECH001'})
MERGE (coop1)-[r31:RELATED_TECH]->(tech1)
SET r31.weight = 0.95, r31.batch_id = 'BATCH-20260412-DEMO';

MATCH (enterprise1:Enterprise {enterprise_id: 'ENT001'}), (tech1:Technology {tech_id: 'TECH001'})
MERGE (enterprise1)-[r32:OWNS_TECH]->(tech1)
SET r32.importance = 0.92, r32.batch_id = 'BATCH-20260412-DEMO';

MATCH (scholar1:Scholar {scholar_id: 'SCH001'}), (tech1:Technology {tech_id: 'TECH001'})
MERGE (scholar1)-[r33:FOCUSES_ON]->(tech1)
SET r33.weight = 0.96, r33.batch_id = 'BATCH-20260412-DEMO';

MATCH (scholar2:Scholar {scholar_id: 'SCH002'}), (tech2:Technology {tech_id: 'TECH002'})
MERGE (scholar2)-[r34:FOCUSES_ON]->(tech2)
SET r34.weight = 0.88, r34.batch_id = 'BATCH-20260412-DEMO';

MATCH (enterprise1:Enterprise {enterprise_id: 'ENT001'}), (seg2:IndustrySegment {segment_id: 'SEG002'})
MERGE (enterprise1)-[r35:BELONGS_TO_SEGMENT]->(seg2)
SET r35.position_name = '中游应用企业', r35.batch_id = 'BATCH-20260412-DEMO';

MATCH (tech1:Technology {tech_id: 'TECH001'}), (seg2:IndustrySegment {segment_id: 'SEG002'})
MERGE (tech1)-[r36:PART_OF_SEGMENT]->(seg2)
SET r36.position_name = '中游关键技术', r36.batch_id = 'BATCH-20260412-DEMO';

MATCH (event1:IndustryEvent {event_id: 'EVENT001'}), (seg2:IndustrySegment {segment_id: 'SEG002'})
MERGE (event1)-[r37:EVENT_IN_SEGMENT]->(seg2)
SET r37.impact_score = 92.5, r37.batch_id = 'BATCH-20260412-DEMO';

MATCH (event1:IndustryEvent {event_id: 'EVENT001'}), (tech1:Technology {tech_id: 'TECH001'})
MERGE (event1)-[r38:EVENT_INVOLVES_TECH]->(tech1)
SET r38.relevance = 0.94, r38.batch_id = 'BATCH-20260412-DEMO';

MATCH (capital1:CapitalEvent {capital_event_id: 'CAP001'}), (enterprise1:Enterprise {enterprise_id: 'ENT001'})
MERGE (capital1)-[r39:INVESTS_IN]->(enterprise1)
SET r39.amount = 5000000.0, r39.event_time = datetime('2025-05-20T10:30:00'), r39.batch_id = 'BATCH-20260412-DEMO';

MATCH (scholar1:Scholar {scholar_id: 'SCH001'}), (team1:Team {team_id: 'TEAM001'})
MERGE (scholar1)-[r40:MEMBER_OF_TEAM]->(team1)
SET r40.role = '负责人', r40.start_date = date('2023-01-01'), r40.end_date = date('2026-12-31'), r40.batch_id = 'BATCH-20260412-DEMO';

MATCH (scholar2:Scholar {scholar_id: 'SCH002'}), (team1:Team {team_id: 'TEAM001'})
MERGE (scholar2)-[r41:MEMBER_OF_TEAM]->(team1)
SET r41.role = '核心成员', r41.start_date = date('2023-01-01'), r41.end_date = date('2026-12-31'), r41.batch_id = 'BATCH-20260412-DEMO';

MATCH (team1:Team {team_id: 'TEAM001'}), (org1:Organization {org_id: 'ORG001'})
MERGE (team1)-[r42:TEAM_IN_ORG]->(org1)
SET r42.batch_id = 'BATCH-20260412-DEMO';

MATCH (paper1:Paper {paper_id: 'PAPER001'}), (award1:Award {award_id: 'AWD001'})
MERGE (paper1)-[r43:WON_AWARD]->(award1)
SET r43.award_year = 2025, r43.batch_id = 'BATCH-20260412-DEMO';

MATCH (path1:InferencePath {path_id: 'PATH001'}), (scholar1:Scholar {scholar_id: 'SCH001'})
MERGE (path1)-[r44:PATH_FROM]->(scholar1)
SET r44.batch_id = 'BATCH-20260412-DEMO';

MATCH (path1:InferencePath {path_id: 'PATH001'}), (scholar3:Scholar {scholar_id: 'SCH003'})
MERGE (path1)-[r45:PATH_TO]->(scholar3)
SET r45.batch_id = 'BATCH-20260412-DEMO';

MATCH (event1:IndustryEvent {event_id: 'EVENT001'}), (report1:TrendReport {report_id: 'TR001'})
MERGE (event1)-[r46:HAS_TREND_REPORT]->(report1)
SET r46.batch_id = 'BATCH-20260412-DEMO';

MATCH (scholar1:Scholar {scholar_id: 'SCH001'}), (batch:UpdateBatch {batch_id: 'BATCH-20260412-DEMO'})
MERGE (scholar1)-[r47:LOADED_IN_BATCH]->(batch)
SET r47.entity_type = 'Scholar', r47.op_type = 'UPSERT';

MATCH (paper1:Paper {paper_id: 'PAPER001'}), (batch:UpdateBatch {batch_id: 'BATCH-20260412-DEMO'})
MERGE (paper1)-[r48:LOADED_IN_BATCH]->(batch)
SET r48.entity_type = 'Paper', r48.op_type = 'UPSERT';

MATCH (patent1:Patent {patent_id: 'PAT001'}), (batch:UpdateBatch {batch_id: 'BATCH-20260412-DEMO'})
MERGE (patent1)-[r49:LOADED_IN_BATCH]->(batch)
SET r49.entity_type = 'Patent', r49.op_type = 'UPSERT';

MATCH (project1:Project {project_id: 'PROJ001'}), (batch:UpdateBatch {batch_id: 'BATCH-20260412-DEMO'})
MERGE (project1)-[r50:LOADED_IN_BATCH]->(batch)
SET r50.entity_type = 'Project', r50.op_type = 'UPSERT';

MATCH (enterprise1:Enterprise {enterprise_id: 'ENT001'}), (batch:UpdateBatch {batch_id: 'BATCH-20260412-DEMO'})
MERGE (enterprise1)-[r51:LOADED_IN_BATCH]->(batch)
SET r51.entity_type = 'Enterprise', r51.op_type = 'UPSERT';


// -----------------------------------------------------------------------------
// 6. 汇总/推理关系
// -----------------------------------------------------------------------------

MATCH (scholar1:Scholar {scholar_id: 'SCH001'}), (scholar2:Scholar {scholar_id: 'SCH002'})
MERGE (scholar1)-[r52:DIRECT_REL]->(scholar2)
SET r52.relation_types_text = '论文合作|专利合作|项目合作',
    r52.coop_count = 3,
    r52.first_time = date('2024-01-01'),
    r52.last_time = date('2025-12-31'),
    r52.evidence_count = 3,
    r52.evidence_ids_text = '["PAPER001","PAT001","PROJ001"]',
    r52.confidence = 0.97,
    r52.rule_version = 'rule_v1',
    r52.version_no = 'v1.0-demo',
    r52.updated_at = datetime('2026-04-12T10:00:00');

MATCH (scholar2:Scholar {scholar_id: 'SCH002'}), (scholar3:Scholar {scholar_id: 'SCH003'})
MERGE (scholar2)-[r53:DIRECT_REL]->(scholar3)
SET r53.relation_types_text = '论文合作',
    r53.coop_count = 1,
    r53.first_time = date('2025-03-15'),
    r53.last_time = date('2025-03-15'),
    r53.evidence_count = 1,
    r53.evidence_ids_text = '["PAPER002"]',
    r53.confidence = 0.81,
    r53.rule_version = 'rule_v1',
    r53.version_no = 'v1.0-demo',
    r53.updated_at = datetime('2026-04-12T10:00:00');

MATCH (scholar1:Scholar {scholar_id: 'SCH001'}), (scholar2:Scholar {scholar_id: 'SCH002'})
MERGE (scholar1)-[r54:PAPER_COOP_REL]->(scholar2)
SET r54.paper_count = 1,
    r54.first_year = 2024,
    r54.last_year = 2024,
    r54.citation_sum = 56,
    r54.journal_level_dist_text = '{"核心期刊":1}',
    r54.common_topics_text = '["知识图谱","科研合作"]',
    r54.team_flag = true,
    r54.influence_score = 89.0,
    r54.version_no = 'v1.0-demo',
    r54.updated_at = datetime('2026-04-12T10:00:00');

MATCH (scholar1:Scholar {scholar_id: 'SCH001'}), (scholar2:Scholar {scholar_id: 'SCH002'})
MERGE (scholar1)-[r55:COLLEAGUE_REL]->(scholar2)
SET r55.org_id = 'ORG001',
    r55.dept_id = 'DEPT001',
    r55.overlap_start = date('2021-01-01'),
    r55.overlap_end = date('2026-12-31'),
    r55.overlap_days = 2191,
    r55.team_background_text = '["计算机科学与技术学院"]',
    r55.evidence_count = 2,
    r55.confidence = 0.99,
    r55.version_no = 'v1.0-demo',
    r55.updated_at = datetime('2026-04-12T10:00:00');

MATCH (scholar1:Scholar {scholar_id: 'SCH001'}), (scholar2:Scholar {scholar_id: 'SCH002'})
MERGE (scholar1)-[r56:ALUMNI_REL]->(scholar2)
SET r56.school_id = 'SCH001',
    r56.college_id = 'COL001',
    r56.relation_subtype = '院友',
    r56.entry_year_gap = 1,
    r56.education_level_text = '["硕士研究生","博士研究生"]',
    r56.evidence_count = 2,
    r56.confidence = 0.91,
    r56.version_no = 'v1.0-demo',
    r56.updated_at = datetime('2026-04-12T10:00:00');

MATCH (scholar1:Scholar {scholar_id: 'SCH001'}), (enterprise1:Enterprise {enterprise_id: 'ENT001'})
MERGE (scholar1)-[r57:EXPERT_ENTERPRISE_REL]->(enterprise1)
SET r57.relation_type = '研发合作',
    r57.role = '首席顾问',
    r57.tech_field_text = '["知识图谱推理","科研评价"]',
    r57.start_date = date('2024-03-01'),
    r57.end_date = date('2026-12-31'),
    r57.coop_mode = '联合研发',
    r57.risk_tag_text = '["低风险"]',
    r57.value_score = 88.0,
    r57.confidence = 0.94,
    r57.version_no = 'v1.0-demo',
    r57.updated_at = datetime('2026-04-12T10:00:00');

MATCH (scholar1:Scholar {scholar_id: 'SCH001'}), (scholar3:Scholar {scholar_id: 'SCH003'})
MERGE (scholar1)-[r58:INDIRECT_REL]->(scholar3)
SET r58.min_path_length = 2,
    r58.strength_score = 78.5,
    r58.relation_label = '潜在合作',
    r58.path_count = 1,
    r58.rule_version = 'rule_v1',
    r58.version_no = 'v1.0-demo',
    r58.generated_at = datetime('2026-04-12T10:00:00');

MATCH (scholar1:Scholar {scholar_id: 'SCH001'}), (scholar2:Scholar {scholar_id: 'SCH002'})
MERGE (scholar1)-[r59:PAIR_COOP_SUMMARY]->(scholar2)
SET r59.paper_count = 1,
    r59.patent_count = 1,
    r59.project_count = 1,
    r59.award_count = 1,
    r59.coop_mode = '长期稳定合作',
    r59.coop_depth_score = 91.0,
    r59.contribution_text = '张三负责总体设计，李四负责图数据库实现与应用。',
    r59.year_dist_text = '{"2024":2,"2025":2}',
    r59.tech_dist_text = '{"知识图谱推理":2,"科研评价":1}',
    r59.updated_at = datetime('2026-04-12T10:00:00');

MATCH (event1:IndustryEvent {event_id: 'EVENT001'}), (scholar1:Scholar {scholar_id: 'SCH001'})
MERGE (event1)-[r60:EVENT_EXPERT_REL]->(scholar1)
SET r60.role = '核心专家',
    r60.relevance = 0.96,
    r60.evidence_count = 2,
    r60.version_no = 'v1.0-demo',
    r60.updated_at = datetime('2026-04-12T10:00:00');

MATCH (event1:IndustryEvent {event_id: 'EVENT001'}), (team1:Team {team_id: 'TEAM001'})
MERGE (event1)-[r61:EVENT_TEAM_REL]->(team1)
SET r61.role = '核心团队',
    r61.relevance = 0.93,
    r61.evidence_count = 1,
    r61.version_no = 'v1.0-demo',
    r61.updated_at = datetime('2026-04-12T10:00:00');

MATCH (seg1:IndustrySegment {segment_id: 'SEG001'}), (seg2:IndustrySegment {segment_id: 'SEG002'})
MERGE (seg1)-[r62:UPSTREAM_OF]->(seg2)
SET r62.weight = 0.88,
    r62.version_no = 'v1.0-demo',
    r62.updated_at = datetime('2026-04-12T10:00:00');

MATCH (seg1:IndustrySegment {segment_id: 'SEG001'}), (seg2:IndustrySegment {segment_id: 'SEG002'})
MERGE (seg1)-[r63:VALUE_FLOW_TO]->(seg2)
SET r63.flow_value = 75.0,
    r63.flow_type = '技术价值传递',
    r63.update_time = datetime('2026-04-12T10:00:00');


// -----------------------------------------------------------------------------
// 7. 导入后验证查询
// -----------------------------------------------------------------------------

MATCH (n)
RETURN count(n) AS total_nodes;

MATCH ()-[r]->()
RETURN count(r) AS total_relationships;
