-- 国内外项目假数据（幂等）：ods_zh/en_project + output
-- 约定：output.id = project.id（源库无外键，入图联通前提）
-- 演示完整子图：fake-zh-proj-001

USE gkx_local;

-- ========== 国内项目主表 ==========
INSERT INTO ods_zh_project (
  id, project_number, title, project_source, funded_institution, project_level,
  funded_amount, discipline, discipline_code, fund_category, funded_province,
  participating_institution, approval_year, approval_time, research_period,
  project_host, participants, keywords, abstract, final_report_abstract,
  project_page_url, create_time, update_time
) VALUES
(
  'fake-zh-proj-001', '62471001', '面向知识图谱的多源异构科技数据融合方法研究',
  '国家自然科学基金(NSFC)', '清华大学', '国家级', 80.00,
  '信息科学-计算机科学-数据库与数据挖掘', 'F-F02-F0202', '面上项目', '北京市',
  '["清华大学","中国科学院计算技术研究所"]',
  '2023-01-01', '2023-01-01', '2023-01-01 至 2026-12-31',
  '张伟',
  '["李娜","王强","赵敏"]',
  '["知识图谱","数据融合","科技情报"]',
  '本项目研究多源异构科技数据的融合建模与图谱构建方法，支撑科技知识图谱应用。',
  '完成了项目—论文—专利跨域关联原型，并在实验室 gkx_local 数据上验证。',
  'https://kd.nsfc.cn/finalDetails?id=fake-zh-proj-001',
  NOW(), NOW()
),
(
  'fake-zh-proj-002', '62471002', '合成孔径雷达抗干扰成像关键技术',
  '国家自然科学基金(NSFC)', '中国科学院空天信息创新研究院', '国家级', 120.00,
  '信息科学-电子学与信息系统-雷达原理与技术', 'F-F01-F0112', '重点项目', '北京市',
  '中国科学院空天信息创新研究院',
  '2022-01-01', '2022-01-01', '2022-01-01 至 2025-12-31',
  '王岩飞', '["刘畅","韩松"]', '["合成孔径雷达","抗干扰","成像"]',
  '研究 SAR 抗干扰成像理论与方法。', '结题摘要样例。',
  'https://kd.nsfc.cn/finalDetails?id=fake-zh-proj-002', NOW(), NOW()
),
(
  'fake-zh-proj-003', '62471003', '干细胞移植治疗心肌梗死的机制研究',
  '国家自然科学基金(NSFC)', '中国人民解放军总医院', '国家级', 66.00,
  '医学科学-循环系统', 'H-H02-H0202', '面上项目', '北京市',
  '中国人民解放军总医院',
  '2021-01-01', '2021-01-01', '2021-01-01 至 2024-12-31',
  '陈韵岱', '["杨俊杰","郭军"]', '["干细胞","心肌梗死","旁分泌"]',
  '研究 GLP-1 对脂肪干细胞移植疗效的影响。', NULL,
  'https://kd.nsfc.cn/finalDetails?id=fake-zh-proj-003', NOW(), NOW()
),
(
  'fake-zh-proj-004', 'S2024A0101', '广东省重点研发计划：智能芯片设计自动化',
  '广东省自然科学基金', '中山大学', '省级', 200.00,
  '信息科学-计算机科学', 'F-F02', '重点研发', '广东省',
  '["中山大学","华为技术有限公司"]',
  '2024-01-01', '2024-03-01', '2024-03-01 至 2027-02-28',
  '黄晓', '["周杰","林芳"]', '["EDA","芯片设计","自动化"]',
  '面向国产工艺的智能芯片设计自动化关键技术。', NULL,
  'https://example.com/fake-zh-proj-004', NOW(), NOW()
),
(
  'fake-zh-proj-005', '62471005', '量子通信网络路由与密钥分发协议',
  '国家自然科学基金(NSFC)', '中国科学技术大学', '国家级', 90.00,
  '信息科学-通信与信息系统', 'F-F01', '面上项目', '安徽省',
  '中国科学技术大学',
  '2023-01-01', '2023-01-01', '2023-01-01 至 2026-12-31',
  '刘洋', '["孙婷"]', '["量子通信","密钥分发","路由"]',
  '研究量子网络路由与 QKD 协议优化。', NULL,
  'https://kd.nsfc.cn/finalDetails?id=fake-zh-proj-005', NOW(), NOW()
),
(
  'fake-zh-proj-006', '62471006', '海洋遥感多源数据同化与预报',
  '国家自然科学基金(NSFC)', '国家海洋局第二海洋研究所', '国家级', 75.00,
  '地球科学-海洋科学', 'D-D06', '面上项目', '浙江省',
  '国家海洋局第二海洋研究所',
  '2020-01-01', '2020-01-01', '2020-01-01 至 2023-12-31',
  '吴涛', '["郑磊"]', '["海洋遥感","数据同化"]',
  '多源海洋遥感数据同化方法研究。', '完成结题。',
  'https://kd.nsfc.cn/finalDetails?id=fake-zh-proj-006', NOW(), NOW()
),
(
  'fake-zh-proj-007', '62471007', '新型锂离子电池固态电解质材料',
  '国家自然科学基金(NSFC)', '北京大学', '国家级', 85.00,
  '化学科学-材料化学', 'B-B05', '面上项目', '北京市',
  '北京大学',
  '2022-01-01', '2022-01-01', '2022-01-01 至 2025-12-31',
  '马超', '["徐静"]', '["固态电解质","锂离子电池"]',
  '设计高离子电导率固态电解质。', NULL,
  'https://kd.nsfc.cn/finalDetails?id=fake-zh-proj-007', NOW(), NOW()
),
(
  'fake-zh-proj-008', '62471008', '城市交通数字孪生与拥堵预测',
  '北京市自然科学基金', '北京交通大学', '省级', 50.00,
  '工学-交通运输工程', NULL, '一般项目', '北京市',
  '["北京交通大学","北京市交通委员会"]',
  '2024-01-01', '2024-06-01', '2024-06-01 至 2026-05-31',
  '何静', '["曹磊","丁一"]', '["数字孪生","交通预测"]',
  '构建城市交通数字孪生与拥堵预测模型。', NULL,
  'https://example.com/fake-zh-proj-008', NOW(), NOW()
)
ON DUPLICATE KEY UPDATE
  title=VALUES(title),
  project_source=VALUES(project_source),
  funded_institution=VALUES(funded_institution),
  project_level=VALUES(project_level),
  funded_amount=VALUES(funded_amount),
  discipline=VALUES(discipline),
  discipline_code=VALUES(discipline_code),
  fund_category=VALUES(fund_category),
  funded_province=VALUES(funded_province),
  participating_institution=VALUES(participating_institution),
  approval_year=VALUES(approval_year),
  approval_time=VALUES(approval_time),
  research_period=VALUES(research_period),
  project_host=VALUES(project_host),
  participants=VALUES(participants),
  keywords=VALUES(keywords),
  abstract=VALUES(abstract),
  final_report_abstract=VALUES(final_report_abstract),
  project_page_url=VALUES(project_page_url),
  update_time=NOW();

-- ========== 国内产出（id 对齐项目） ==========
INSERT INTO ods_zh_project_output (
  id, total_outputs, journal_articles_count, conference_papers_count, books_count,
  degree_papers_count, patents_count, clinical_trials_count, products_count,
  awards_count, reports_count, other_outputs_count,
  output_journal_articles, output_conference_papers, output_books, output_degree_papers,
  output_patents, output_clinical_trials, output_products, output_awards,
  output_reports, output_other, create_time, update_time
) VALUES
(
  'fake-zh-proj-001', 2, 1, 0, NULL, NULL, 1, NULL, NULL, NULL, NULL, NULL,
  '[{"title":"多源科技数据融合的知识图谱构建方法","authors":["张伟","李娜"],"journal":"计算机学报","doi":"10.fake/zh.proj.001.paper","year":2024}]',
  NULL, NULL, NULL,
  '[{"patent_title":"一种科技知识图谱实体对齐装置","patent_number":"CN201811394750.6","patent_inventor":["张伟","王强"]}]',
  NULL, NULL, NULL, NULL, NULL, NOW(), NOW()
),
(
  'fake-zh-proj-002', 2, 1, 0, NULL, NULL, 1, NULL, NULL, NULL, NULL, NULL,
  '[{"title":"SAR抗干扰成像算法","authors":["王岩飞","刘畅"],"journal":"电子学报","year":2023}]',
  NULL, NULL, NULL,
  '[{"patent_title":"一种实现SAR抗干扰的多脉冲组合成像方法","patent_number":"201811394750.6","patent_inventor":["王岩飞","韩松"]}]',
  NULL, NULL, NULL, NULL, NULL, NOW(), NOW()
),
(
  'fake-zh-proj-003', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
  '[{"title":"GLP-1对脂肪干细胞移植的保护作用","authors":["陈韵岱"],"journal":"中华心血管病杂志","year":2022}]',
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()
),
(
  'fake-zh-proj-004', 1, NULL, NULL, NULL, NULL, 1, NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"patent_title":"一种芯片布局布线优化方法","patent_number":"CN202410000001.X","patent_inventor":["黄晓"]}]',
  NULL, NULL, NULL, NULL, NULL, NOW(), NOW()
),
(
  'fake-zh-proj-005', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
  '[{"title":"量子网络路由协议仿真","authors":["刘洋"],"journal":"通信学报","doi":"10.fake/zh.proj.005","year":2024}]',
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()
),
(
  'fake-zh-proj-006', 0, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()
),
(
  'fake-zh-proj-007', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
  '[{"title":"高电导率固态电解质材料进展","authors":["马超"],"journal":"化学学报","year":2023}]',
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()
),
(
  'fake-zh-proj-008', 1, NULL, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
  NULL,
  '[{"title":"Urban traffic twin for congestion prediction","authors":["何静"],"year":2025,"doi":"10.fake/zh.proj.008","name":"ITSC"}]',
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()
)
ON DUPLICATE KEY UPDATE
  total_outputs=VALUES(total_outputs),
  journal_articles_count=VALUES(journal_articles_count),
  conference_papers_count=VALUES(conference_papers_count),
  patents_count=VALUES(patents_count),
  output_journal_articles=VALUES(output_journal_articles),
  output_conference_papers=VALUES(output_conference_papers),
  output_patents=VALUES(output_patents),
  update_time=NOW();

-- ========== 国外项目主表 ==========
INSERT INTO ods_en_project (
  id, project_number, title, project_source, funded_institution, project_level,
  funded_amount, discipline, discipline_code, fund_category, funded_province,
  participating_institution, approval_year, approval_time, research_period,
  project_host, participants, keywords, abstract, project_page_url,
  create_time, update_time
) VALUES
(
  'fake-en-proj-001', '2331357',
  'ART: Knowledge Graph Fusion for Translational Research Excellence',
  '美国国家科学基金(NSF)', 'FLORIDA STATE UNIVERSITY', '国家级', 5992385.00,
  NULL, NULL, 'Cooperative Agreement', NULL,
  '["FLORIDA STATE UNIVERSITY","MIT"]',
  '2024-01-01', '2024-02-01', '2024-02-01 至 2028-01-31',
  'Stacey S Patterson',
  '["Mark A Riley","Janet A Kistner"]',
  '["knowledge graph","translational research","data fusion"]',
  'This project builds multi-source knowledge graphs for translational research.',
  'https://www.nsf.gov/awardsearch/show-award/?AWD_ID=2331357-fake',
  NOW(), NOW()
),
(
  'fake-en-proj-002', '2029378',
  'EAGER: Detection and Analysis of Airborne Coronavirus with Bioinspired Membranes',
  '美国国家科学基金(NSF)', 'University of Maine', '国家级', 154057.00,
  NULL, NULL, 'Standard Grant', NULL, 'University of Maine',
  '2020-01-01', '2020-08-01', '2020-08-01 至 2022-07-31',
  'Caitlin Howell', '["Melissa Maginnis"]',
  '["COVID-19","bioinspired membranes","sensors"]',
  'Detection of airborne pathogens using bioinspired membranes.',
  'https://www.nsf.gov/awardsearch/show-award/?AWD_ID=2029378-fake',
  NOW(), NOW()
),
(
  'fake-en-proj-003', 'HORIZON-2024-CL4-01',
  'EU Horizon: Trusted AI for Scientific Discovery',
  '欧盟地平线计划(Horizon Europe)', 'Technical University of Munich', '国际级', 2500000.00,
  NULL, NULL, 'RIA', NULL,
  '["Technical University of Munich","University of Oxford"]',
  '2024-01-01', '2024-05-01', '2024-05-01 至 2027-04-30',
  'Anna Schmidt', '["James Brown","Maria Rossi"]',
  '["trusted AI","scientific discovery"]',
  'Developing trusted AI methods for scientific discovery pipelines.',
  'https://cordis.europa.eu/project/fake-en-proj-003',
  NOW(), NOW()
),
(
  'fake-en-proj-004', 'NSF-2145001',
  'Collaborative Research: Graph Neural Networks for Materials Discovery',
  '美国国家科学基金(NSF)', 'Stanford University', '国家级', 450000.00,
  NULL, NULL, 'Standard Grant', NULL, 'Stanford University',
  '2022-01-01', '2022-09-01', '2022-09-01 至 2025-08-31',
  'Emily Chen', '["Robert Kim"]',
  '["GNN","materials discovery"]',
  'Graph neural networks for accelerating materials discovery.',
  'https://www.nsf.gov/awardsearch/show-award/?AWD_ID=2145001-fake',
  NOW(), NOW()
),
(
  'fake-en-proj-005', 'EPSRC-EP/X12345/1',
  'Quantum Network Protocols for Secure Communications',
  '英国工程与物理科学研究理事会(EPSRC)', 'University of Cambridge', '国家级', 780000.00,
  NULL, NULL, 'Standard Grant', NULL, 'University of Cambridge',
  '2023-01-01', '2023-04-01', '2023-04-01 至 2026-03-31',
  'David Wilson', '["Sophie Turner"]',
  '["quantum network","secure communications"]',
  'Protocols for quantum-secure communication networks.',
  'https://gtr.ukri.org/projects/fake-en-proj-005',
  NOW(), NOW()
),
(
  'fake-en-proj-006', 'JSPS-KAKENHI-24H00001',
  'Ocean Remote Sensing Data Assimilation for Climate Prediction',
  '日本学术振兴会(JSPS)', 'University of Tokyo', '国家级', 320000.00,
  NULL, NULL, 'KAKENHI', NULL, 'University of Tokyo',
  '2024-01-01', '2024-04-01', '2024-04-01 至 2027-03-31',
  'Hiroshi Tanaka', '["Yuki Sato"]',
  '["ocean remote sensing","data assimilation"]',
  'Multi-source ocean remote sensing assimilation methods.',
  'https://kaken.nii.ac.jp/fake-en-proj-006',
  NOW(), NOW()
),
(
  'fake-en-proj-007', 'DFG-TRR-401',
  'Solid-State Electrolytes for Next-Generation Batteries',
  '德国研究联合会(DFG)', 'RWTH Aachen University', '国家级', 1100000.00,
  NULL, NULL, 'Collaborative Research Centre', NULL, 'RWTH Aachen University',
  '2021-01-01', '2021-01-01', '2021-01-01 至 2024-12-31',
  'Klaus Mueller', '["Lena Hoffmann"]',
  '["solid-state electrolyte","batteries"]',
  'Design of high-conductivity solid-state electrolytes.',
  'https://gepris.dfg.de/fake-en-proj-007',
  NOW(), NOW()
),
(
  'fake-en-proj-008', 'ARC-DP2401001',
  'Digital Twins for Urban Mobility and Congestion Mitigation',
  '澳大利亚研究理事会(ARC)', 'University of Melbourne', '国家级', 510000.00,
  NULL, NULL, 'Discovery Project', NULL,
  '["University of Melbourne","Monash University"]',
  '2024-01-01', '2024-07-01', '2024-07-01 至 2027-06-30',
  'Olivia Parker', '["Noah Harris"]',
  '["digital twin","urban mobility"]',
  'Urban mobility digital twins for congestion mitigation.',
  'https://dataportal.arc.gov.au/fake-en-proj-008',
  NOW(), NOW()
)
ON DUPLICATE KEY UPDATE
  title=VALUES(title),
  project_source=VALUES(project_source),
  funded_institution=VALUES(funded_institution),
  project_level=VALUES(project_level),
  funded_amount=VALUES(funded_amount),
  fund_category=VALUES(fund_category),
  participating_institution=VALUES(participating_institution),
  approval_year=VALUES(approval_year),
  approval_time=VALUES(approval_time),
  research_period=VALUES(research_period),
  project_host=VALUES(project_host),
  participants=VALUES(participants),
  keywords=VALUES(keywords),
  abstract=VALUES(abstract),
  project_page_url=VALUES(project_page_url),
  update_time=NOW();

-- ========== 国外产出 ==========
INSERT INTO ods_en_project_output (
  id, total_outputs, journal_articles_count, conference_papers_count, books_count,
  degree_papers_count, patents_count, clinical_trials_count, products_count,
  awards_count, reports_count, other_outputs_count,
  output_journal_articles, output_conference_papers, output_books, output_degree_papers,
  output_patents, output_clinical_trials, output_products, output_awards,
  output_reports, output_other, create_time, update_time
) VALUES
(
  'fake-en-proj-001', 2, 1, 0, NULL, NULL, 1, NULL, NULL, NULL, NULL, NULL,
  '[{"title":"Knowledge Graph Fusion for Translational Research","authors":["Stacey S Patterson"],"journal":"Nature Communications","doi":"10.fake/en.proj.001.paper","year":2025}]',
  NULL, NULL, NULL,
  '[{"patent_title":"System for entity alignment in science graphs","patent_number":"US20240123456A1","patent_inventor":["Stacey S Patterson"]}]',
  NULL, NULL, NULL, NULL, NULL, NOW(), NOW()
),
(
  'fake-en-proj-002', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
  '[{"title":"Variable-Area Sensor for Aqueous Analytes","authors":["Caitlin Howell"],"journal":"ACS Sensors","year":2024}]',
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()
),
(
  'fake-en-proj-003', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
  '[{"title":"Trusted AI Pipelines for Scientific Discovery","authors":["Anna Schmidt"],"doi":"10.fake/en.proj.003","year":2025}]',
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()
),
(
  'fake-en-proj-004', 1, NULL, NULL, NULL, NULL, 1, NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"patent_title":"GNN-based materials screening apparatus","patent_number":"US11223344B2","patent_inventor":["Emily Chen"]}]',
  NULL, NULL, NULL, NULL, NULL, NOW(), NOW()
),
(
  'fake-en-proj-005', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
  '[{"title":"Quantum network routing under noise","authors":["David Wilson"],"journal":"Physical Review Applied","year":2024}]',
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()
),
(
  'fake-en-proj-006', 0, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()
),
(
  'fake-en-proj-007', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
  '[{"title":"High-conductivity solid electrolytes","authors":["Klaus Mueller"],"journal":"Advanced Energy Materials","year":2023}]',
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()
),
(
  'fake-en-proj-008', 1, NULL, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
  NULL,
  '[{"title":"Digital twins for urban congestion mitigation","authors":["Olivia Parker"],"year":2025,"doi":"10.fake/en.proj.008","name":"ACM SIGSPATIAL"}]',
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()
)
ON DUPLICATE KEY UPDATE
  total_outputs=VALUES(total_outputs),
  journal_articles_count=VALUES(journal_articles_count),
  conference_papers_count=VALUES(conference_papers_count),
  patents_count=VALUES(patents_count),
  output_journal_articles=VALUES(output_journal_articles),
  output_conference_papers=VALUES(output_conference_papers),
  output_patents=VALUES(output_patents),
  update_time=NOW();

-- 可选关系表：gkx_local 当前不存在 dwd_rel_project_paper / dwd_rel_project_patent，故不建。
-- 若后续建表，可插入：
-- INSERT INTO dwd_rel_project_paper (project_id, paper_id) VALUES ('fake-zh-proj-001', 'fake_proj_001');
-- INSERT INTO dwd_rel_project_patent (project_id, patent_id) VALUES ('fake-zh-proj-001', 'CN201811394750.6');
