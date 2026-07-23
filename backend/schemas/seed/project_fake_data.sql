-- 国内外项目假数据：各 50 条，对齐现网 gkx_element.dwd_*
-- 约定：output.id = project.id；演示：fake-zh-proj-001
-- 现网 id 无主键；重灌前先 DELETE … WHERE id LIKE 'fake-%'

USE gkx_element;

INSERT INTO dwd_zh_project (
  id, project_number, title, project_source, funded_institution, project_level,
  funded_amount, discipline, discipline_code, fund_category, funded_province,
  participating_institution, approval_year, approval_time, research_period,
  project_host, participants, keywords, abstract, final_report_abstract,
  project_page_url, updated_time
) VALUES
(
  'fake-zh-proj-001', 'FZ62471001', '面向知识图谱的多源异构科技数据融合方法研究（样例001）',
  '国家自然科学基金(NSFC)', '清华大学', '国家级', 55.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["清华大学", "北京大学"]',
  2018, '2018-01-01', '2018-01-01 至 2021-12-31',
  '张伟',
  '["张伟", "王岩飞", "陈韵岱"]',
  '["知识图谱", "数据融合", "主题1"]',
  '假数据摘要：项目 fake-zh-proj-001 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-001',
  NOW()
),
(
  'fake-zh-proj-002', 'FZ62471002', '合成孔径雷达抗干扰成像关键技术（样例002）',
  '国家自然科学基金(NSFC)', '北京大学', '国家级', 60.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["北京大学", "中国科学技术大学"]',
  2019, '2019-01-01', '2019-01-01 至 2022-12-31',
  '王岩飞',
  '["王岩飞", "陈韵岱", "黄晓"]',
  '["知识图谱", "数据融合", "主题2"]',
  '假数据摘要：项目 fake-zh-proj-002 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-002',
  NOW()
),
(
  'fake-zh-proj-003', 'FZ62471003', '干细胞移植治疗心肌梗死的机制研究（样例003）',
  '国家自然科学基金(NSFC)', '中国科学技术大学', '国家级', 65.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["中国科学技术大学", "中山大学"]',
  2020, '2020-01-01', '2020-01-01 至 2023-12-31',
  '陈韵岱',
  '["陈韵岱", "黄晓", "刘洋"]',
  '["知识图谱", "数据融合", "主题3"]',
  '假数据摘要：项目 fake-zh-proj-003 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-003',
  NOW()
),
(
  'fake-zh-proj-004', 'FZ62471004', '智能芯片设计自动化关键技术（样例004）',
  '国家自然科学基金(NSFC)', '中山大学', '国家级', 70.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["中山大学", "北京交通大学"]',
  2021, '2021-01-01', '2021-01-01 至 2024-12-31',
  '黄晓',
  '["黄晓", "刘洋", "吴涛"]',
  '["知识图谱", "数据融合", "主题4"]',
  '假数据摘要：项目 fake-zh-proj-004 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-004',
  NOW()
),
(
  'fake-zh-proj-005', 'FZ62471005', '量子通信网络路由与密钥分发协议（样例005）',
  '国家自然科学基金(NSFC)', '北京交通大学', '国家级', 75.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["北京交通大学", "中国科学院计算技术研究所"]',
  2022, '2022-01-01', '2022-01-01 至 2025-12-31',
  '刘洋',
  '["刘洋", "吴涛", "马超"]',
  '["知识图谱", "数据融合", "主题5"]',
  '假数据摘要：项目 fake-zh-proj-005 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-005',
  NOW()
),
(
  'fake-zh-proj-006', 'FZ62471006', '海洋遥感多源数据同化与预报（样例006）',
  '国家自然科学基金(NSFC)', '中国科学院计算技术研究所', '国家级', 80.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["中国科学院计算技术研究所", "复旦大学"]',
  2023, '2023-01-01', '2023-01-01 至 2026-12-31',
  '吴涛',
  '["吴涛", "马超", "何静"]',
  '["知识图谱", "数据融合", "主题6"]',
  '假数据摘要：项目 fake-zh-proj-006 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-006',
  NOW()
),
(
  'fake-zh-proj-007', 'FZ62471007', '新型锂离子电池固态电解质材料（样例007）',
  '国家自然科学基金(NSFC)', '复旦大学', '国家级', 85.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["复旦大学", "上海交通大学"]',
  2024, '2024-01-01', '2024-01-01 至 2027-12-31',
  '马超',
  '["马超", "何静", "李娜"]',
  '["知识图谱", "数据融合", "主题7"]',
  '假数据摘要：项目 fake-zh-proj-007 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-007',
  NOW()
),
(
  'fake-zh-proj-008', 'FZ62471008', '城市交通数字孪生与拥堵预测（样例008）',
  '国家自然科学基金(NSFC)', '上海交通大学', '国家级', 90.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["上海交通大学", "浙江大学"]',
  2018, '2018-01-01', '2018-01-01 至 2021-12-31',
  '何静',
  '["何静", "李娜", "赵敏"]',
  '["知识图谱", "数据融合", "主题8"]',
  '假数据摘要：项目 fake-zh-proj-008 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-008',
  NOW()
),
(
  'fake-zh-proj-009', 'FZ62471009', '大模型驱动的科技情报抽取与推理（样例009）',
  '国家自然科学基金(NSFC)', '浙江大学', '国家级', 95.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["浙江大学", "南京大学"]',
  2019, '2019-01-01', '2019-01-01 至 2022-12-31',
  '李娜',
  '["李娜", "赵敏", "周杰"]',
  '["知识图谱", "数据融合", "主题9"]',
  '假数据摘要：项目 fake-zh-proj-009 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-009',
  NOW()
),
(
  'fake-zh-proj-010', 'FZ62471010', '工业互联网边缘协同调度优化（样例010）',
  '国家自然科学基金(NSFC)', '南京大学', '国家级', 100.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["南京大学", "清华大学"]',
  2020, '2020-01-01', '2020-01-01 至 2023-12-31',
  '赵敏',
  '["赵敏", "周杰", "林芳"]',
  '["知识图谱", "数据融合", "主题10"]',
  '假数据摘要：项目 fake-zh-proj-010 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-010',
  NOW()
),
(
  'fake-zh-proj-011', 'FZ62471011', '面向知识图谱的多源异构科技数据融合方法研究（样例011）',
  '国家自然科学基金(NSFC)', '清华大学', '国家级', 105.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["清华大学", "北京大学"]',
  2021, '2021-01-01', '2021-01-01 至 2024-12-31',
  '周杰',
  '["周杰", "林芳", "孙婷"]',
  '["知识图谱", "数据融合", "主题11"]',
  '假数据摘要：项目 fake-zh-proj-011 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-011',
  NOW()
),
(
  'fake-zh-proj-012', 'FZ62471012', '合成孔径雷达抗干扰成像关键技术（样例012）',
  '国家自然科学基金(NSFC)', '北京大学', '国家级', 110.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["北京大学", "中国科学技术大学"]',
  2022, '2022-01-01', '2022-01-01 至 2025-12-31',
  '林芳',
  '["林芳", "孙婷", "郑磊"]',
  '["知识图谱", "数据融合", "主题12"]',
  '假数据摘要：项目 fake-zh-proj-012 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-012',
  NOW()
),
(
  'fake-zh-proj-013', 'FZ62471013', '干细胞移植治疗心肌梗死的机制研究（样例013）',
  '国家自然科学基金(NSFC)', '中国科学技术大学', '国家级', 115.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["中国科学技术大学", "中山大学"]',
  2023, '2023-01-01', '2023-01-01 至 2026-12-31',
  '孙婷',
  '["孙婷", "郑磊", "徐静"]',
  '["知识图谱", "数据融合", "主题13"]',
  '假数据摘要：项目 fake-zh-proj-013 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-013',
  NOW()
),
(
  'fake-zh-proj-014', 'FZ62471014', '智能芯片设计自动化关键技术（样例014）',
  '国家自然科学基金(NSFC)', '中山大学', '国家级', 120.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["中山大学", "北京交通大学"]',
  2024, '2024-01-01', '2024-01-01 至 2027-12-31',
  '郑磊',
  '["郑磊", "徐静", "曹磊"]',
  '["知识图谱", "数据融合", "主题14"]',
  '假数据摘要：项目 fake-zh-proj-014 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-014',
  NOW()
),
(
  'fake-zh-proj-015', 'FZ62471015', '量子通信网络路由与密钥分发协议（样例015）',
  '国家自然科学基金(NSFC)', '北京交通大学', '国家级', 125.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["北京交通大学", "中国科学院计算技术研究所"]',
  2018, '2018-01-01', '2018-01-01 至 2021-12-31',
  '徐静',
  '["徐静", "曹磊", "丁一"]',
  '["知识图谱", "数据融合", "主题15"]',
  '假数据摘要：项目 fake-zh-proj-015 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-015',
  NOW()
),
(
  'fake-zh-proj-016', 'FZ62471016', '海洋遥感多源数据同化与预报（样例016）',
  '国家自然科学基金(NSFC)', '中国科学院计算技术研究所', '国家级', 130.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["中国科学院计算技术研究所", "复旦大学"]',
  2019, '2019-01-01', '2019-01-01 至 2022-12-31',
  '曹磊',
  '["曹磊", "丁一", "韩松"]',
  '["知识图谱", "数据融合", "主题16"]',
  '假数据摘要：项目 fake-zh-proj-016 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-016',
  NOW()
),
(
  'fake-zh-proj-017', 'FZ62471017', '新型锂离子电池固态电解质材料（样例017）',
  '国家自然科学基金(NSFC)', '复旦大学', '国家级', 135.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["复旦大学", "上海交通大学"]',
  2020, '2020-01-01', '2020-01-01 至 2023-12-31',
  '丁一',
  '["丁一", "韩松", "郭军"]',
  '["知识图谱", "数据融合", "主题17"]',
  '假数据摘要：项目 fake-zh-proj-017 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-017',
  NOW()
),
(
  'fake-zh-proj-018', 'FZ62471018', '城市交通数字孪生与拥堵预测（样例018）',
  '国家自然科学基金(NSFC)', '上海交通大学', '国家级', 140.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["上海交通大学", "浙江大学"]',
  2021, '2021-01-01', '2021-01-01 至 2024-12-31',
  '韩松',
  '["韩松", "郭军", "杨俊杰"]',
  '["知识图谱", "数据融合", "主题18"]',
  '假数据摘要：项目 fake-zh-proj-018 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-018',
  NOW()
),
(
  'fake-zh-proj-019', 'FZ62471019', '大模型驱动的科技情报抽取与推理（样例019）',
  '国家自然科学基金(NSFC)', '浙江大学', '国家级', 145.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["浙江大学", "南京大学"]',
  2022, '2022-01-01', '2022-01-01 至 2025-12-31',
  '郭军',
  '["郭军", "杨俊杰", "张伟"]',
  '["知识图谱", "数据融合", "主题19"]',
  '假数据摘要：项目 fake-zh-proj-019 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-019',
  NOW()
),
(
  'fake-zh-proj-020', 'FZ62471020', '工业互联网边缘协同调度优化（样例020）',
  '国家自然科学基金(NSFC)', '南京大学', '国家级', 50.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["南京大学", "清华大学"]',
  2023, '2023-01-01', '2023-01-01 至 2026-12-31',
  '杨俊杰',
  '["杨俊杰", "张伟", "王岩飞"]',
  '["知识图谱", "数据融合", "主题20"]',
  '假数据摘要：项目 fake-zh-proj-020 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-020',
  NOW()
),
(
  'fake-zh-proj-021', 'FZ62471021', '面向知识图谱的多源异构科技数据融合方法研究（样例021）',
  '国家自然科学基金(NSFC)', '清华大学', '国家级', 55.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["清华大学", "北京大学"]',
  2024, '2024-01-01', '2024-01-01 至 2027-12-31',
  '张伟',
  '["张伟", "王岩飞", "陈韵岱"]',
  '["知识图谱", "数据融合", "主题21"]',
  '假数据摘要：项目 fake-zh-proj-021 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-021',
  NOW()
),
(
  'fake-zh-proj-022', 'FZ62471022', '合成孔径雷达抗干扰成像关键技术（样例022）',
  '国家自然科学基金(NSFC)', '北京大学', '国家级', 60.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["北京大学", "中国科学技术大学"]',
  2018, '2018-01-01', '2018-01-01 至 2021-12-31',
  '王岩飞',
  '["王岩飞", "陈韵岱", "黄晓"]',
  '["知识图谱", "数据融合", "主题22"]',
  '假数据摘要：项目 fake-zh-proj-022 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-022',
  NOW()
),
(
  'fake-zh-proj-023', 'FZ62471023', '干细胞移植治疗心肌梗死的机制研究（样例023）',
  '国家自然科学基金(NSFC)', '中国科学技术大学', '国家级', 65.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["中国科学技术大学", "中山大学"]',
  2019, '2019-01-01', '2019-01-01 至 2022-12-31',
  '陈韵岱',
  '["陈韵岱", "黄晓", "刘洋"]',
  '["知识图谱", "数据融合", "主题23"]',
  '假数据摘要：项目 fake-zh-proj-023 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-023',
  NOW()
),
(
  'fake-zh-proj-024', 'FZ62471024', '智能芯片设计自动化关键技术（样例024）',
  '国家自然科学基金(NSFC)', '中山大学', '国家级', 70.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["中山大学", "北京交通大学"]',
  2020, '2020-01-01', '2020-01-01 至 2023-12-31',
  '黄晓',
  '["黄晓", "刘洋", "吴涛"]',
  '["知识图谱", "数据融合", "主题24"]',
  '假数据摘要：项目 fake-zh-proj-024 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-024',
  NOW()
),
(
  'fake-zh-proj-025', 'FZ62471025', '量子通信网络路由与密钥分发协议（样例025）',
  '国家自然科学基金(NSFC)', '北京交通大学', '国家级', 75.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["北京交通大学", "中国科学院计算技术研究所"]',
  2021, '2021-01-01', '2021-01-01 至 2024-12-31',
  '刘洋',
  '["刘洋", "吴涛", "马超"]',
  '["知识图谱", "数据融合", "主题25"]',
  '假数据摘要：项目 fake-zh-proj-025 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-025',
  NOW()
),
(
  'fake-zh-proj-026', 'FZ62471026', '海洋遥感多源数据同化与预报（样例026）',
  '国家自然科学基金(NSFC)', '中国科学院计算技术研究所', '国家级', 80.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["中国科学院计算技术研究所", "复旦大学"]',
  2022, '2022-01-01', '2022-01-01 至 2025-12-31',
  '吴涛',
  '["吴涛", "马超", "何静"]',
  '["知识图谱", "数据融合", "主题26"]',
  '假数据摘要：项目 fake-zh-proj-026 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-026',
  NOW()
),
(
  'fake-zh-proj-027', 'FZ62471027', '新型锂离子电池固态电解质材料（样例027）',
  '国家自然科学基金(NSFC)', '复旦大学', '国家级', 85.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["复旦大学", "上海交通大学"]',
  2023, '2023-01-01', '2023-01-01 至 2026-12-31',
  '马超',
  '["马超", "何静", "李娜"]',
  '["知识图谱", "数据融合", "主题27"]',
  '假数据摘要：项目 fake-zh-proj-027 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-027',
  NOW()
),
(
  'fake-zh-proj-028', 'FZ62471028', '城市交通数字孪生与拥堵预测（样例028）',
  '国家自然科学基金(NSFC)', '上海交通大学', '国家级', 90.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["上海交通大学", "浙江大学"]',
  2024, '2024-01-01', '2024-01-01 至 2027-12-31',
  '何静',
  '["何静", "李娜", "赵敏"]',
  '["知识图谱", "数据融合", "主题28"]',
  '假数据摘要：项目 fake-zh-proj-028 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-028',
  NOW()
),
(
  'fake-zh-proj-029', 'FZ62471029', '大模型驱动的科技情报抽取与推理（样例029）',
  '国家自然科学基金(NSFC)', '浙江大学', '国家级', 95.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["浙江大学", "南京大学"]',
  2018, '2018-01-01', '2018-01-01 至 2021-12-31',
  '李娜',
  '["李娜", "赵敏", "周杰"]',
  '["知识图谱", "数据融合", "主题29"]',
  '假数据摘要：项目 fake-zh-proj-029 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-029',
  NOW()
),
(
  'fake-zh-proj-030', 'FZ62471030', '工业互联网边缘协同调度优化（样例030）',
  '国家自然科学基金(NSFC)', '南京大学', '国家级', 100.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["南京大学", "清华大学"]',
  2019, '2019-01-01', '2019-01-01 至 2022-12-31',
  '赵敏',
  '["赵敏", "周杰", "林芳"]',
  '["知识图谱", "数据融合", "主题30"]',
  '假数据摘要：项目 fake-zh-proj-030 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-030',
  NOW()
),
(
  'fake-zh-proj-031', 'FZ62471031', '面向知识图谱的多源异构科技数据融合方法研究（样例031）',
  '国家自然科学基金(NSFC)', '清华大学', '国家级', 105.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["清华大学", "北京大学"]',
  2020, '2020-01-01', '2020-01-01 至 2023-12-31',
  '周杰',
  '["周杰", "林芳", "孙婷"]',
  '["知识图谱", "数据融合", "主题31"]',
  '假数据摘要：项目 fake-zh-proj-031 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-031',
  NOW()
),
(
  'fake-zh-proj-032', 'FZ62471032', '合成孔径雷达抗干扰成像关键技术（样例032）',
  '国家自然科学基金(NSFC)', '北京大学', '国家级', 110.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["北京大学", "中国科学技术大学"]',
  2021, '2021-01-01', '2021-01-01 至 2024-12-31',
  '林芳',
  '["林芳", "孙婷", "郑磊"]',
  '["知识图谱", "数据融合", "主题32"]',
  '假数据摘要：项目 fake-zh-proj-032 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-032',
  NOW()
),
(
  'fake-zh-proj-033', 'FZ62471033', '干细胞移植治疗心肌梗死的机制研究（样例033）',
  '国家自然科学基金(NSFC)', '中国科学技术大学', '国家级', 115.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["中国科学技术大学", "中山大学"]',
  2022, '2022-01-01', '2022-01-01 至 2025-12-31',
  '孙婷',
  '["孙婷", "郑磊", "徐静"]',
  '["知识图谱", "数据融合", "主题33"]',
  '假数据摘要：项目 fake-zh-proj-033 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-033',
  NOW()
),
(
  'fake-zh-proj-034', 'FZ62471034', '智能芯片设计自动化关键技术（样例034）',
  '国家自然科学基金(NSFC)', '中山大学', '国家级', 120.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["中山大学", "北京交通大学"]',
  2023, '2023-01-01', '2023-01-01 至 2026-12-31',
  '郑磊',
  '["郑磊", "徐静", "曹磊"]',
  '["知识图谱", "数据融合", "主题34"]',
  '假数据摘要：项目 fake-zh-proj-034 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-034',
  NOW()
),
(
  'fake-zh-proj-035', 'FZ62471035', '量子通信网络路由与密钥分发协议（样例035）',
  '国家自然科学基金(NSFC)', '北京交通大学', '国家级', 125.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["北京交通大学", "中国科学院计算技术研究所"]',
  2024, '2024-01-01', '2024-01-01 至 2027-12-31',
  '徐静',
  '["徐静", "曹磊", "丁一"]',
  '["知识图谱", "数据融合", "主题35"]',
  '假数据摘要：项目 fake-zh-proj-035 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-035',
  NOW()
),
(
  'fake-zh-proj-036', 'FZ62471036', '海洋遥感多源数据同化与预报（样例036）',
  '国家自然科学基金(NSFC)', '中国科学院计算技术研究所', '国家级', 130.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["中国科学院计算技术研究所", "复旦大学"]',
  2018, '2018-01-01', '2018-01-01 至 2021-12-31',
  '曹磊',
  '["曹磊", "丁一", "韩松"]',
  '["知识图谱", "数据融合", "主题36"]',
  '假数据摘要：项目 fake-zh-proj-036 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-036',
  NOW()
),
(
  'fake-zh-proj-037', 'FZ62471037', '新型锂离子电池固态电解质材料（样例037）',
  '国家自然科学基金(NSFC)', '复旦大学', '国家级', 135.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["复旦大学", "上海交通大学"]',
  2019, '2019-01-01', '2019-01-01 至 2022-12-31',
  '丁一',
  '["丁一", "韩松", "郭军"]',
  '["知识图谱", "数据融合", "主题37"]',
  '假数据摘要：项目 fake-zh-proj-037 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-037',
  NOW()
),
(
  'fake-zh-proj-038', 'FZ62471038', '城市交通数字孪生与拥堵预测（样例038）',
  '国家自然科学基金(NSFC)', '上海交通大学', '国家级', 140.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["上海交通大学", "浙江大学"]',
  2020, '2020-01-01', '2020-01-01 至 2023-12-31',
  '韩松',
  '["韩松", "郭军", "杨俊杰"]',
  '["知识图谱", "数据融合", "主题38"]',
  '假数据摘要：项目 fake-zh-proj-038 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-038',
  NOW()
),
(
  'fake-zh-proj-039', 'FZ62471039', '大模型驱动的科技情报抽取与推理（样例039）',
  '国家自然科学基金(NSFC)', '浙江大学', '国家级', 145.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["浙江大学", "南京大学"]',
  2021, '2021-01-01', '2021-01-01 至 2024-12-31',
  '郭军',
  '["郭军", "杨俊杰", "张伟"]',
  '["知识图谱", "数据融合", "主题39"]',
  '假数据摘要：项目 fake-zh-proj-039 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-039',
  NOW()
),
(
  'fake-zh-proj-040', 'FZ62471040', '工业互联网边缘协同调度优化（样例040）',
  '国家自然科学基金(NSFC)', '南京大学', '国家级', 50.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["南京大学", "清华大学"]',
  2022, '2022-01-01', '2022-01-01 至 2025-12-31',
  '杨俊杰',
  '["杨俊杰", "张伟", "王岩飞"]',
  '["知识图谱", "数据融合", "主题40"]',
  '假数据摘要：项目 fake-zh-proj-040 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-040',
  NOW()
),
(
  'fake-zh-proj-041', 'FZ62471041', '面向知识图谱的多源异构科技数据融合方法研究（样例041）',
  '国家自然科学基金(NSFC)', '清华大学', '国家级', 55.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["清华大学", "北京大学"]',
  2023, '2023-01-01', '2023-01-01 至 2026-12-31',
  '张伟',
  '["张伟", "王岩飞", "陈韵岱"]',
  '["知识图谱", "数据融合", "主题41"]',
  '假数据摘要：项目 fake-zh-proj-041 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-041',
  NOW()
),
(
  'fake-zh-proj-042', 'FZ62471042', '合成孔径雷达抗干扰成像关键技术（样例042）',
  '国家自然科学基金(NSFC)', '北京大学', '国家级', 60.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["北京大学", "中国科学技术大学"]',
  2024, '2024-01-01', '2024-01-01 至 2027-12-31',
  '王岩飞',
  '["王岩飞", "陈韵岱", "黄晓"]',
  '["知识图谱", "数据融合", "主题42"]',
  '假数据摘要：项目 fake-zh-proj-042 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-042',
  NOW()
),
(
  'fake-zh-proj-043', 'FZ62471043', '干细胞移植治疗心肌梗死的机制研究（样例043）',
  '国家自然科学基金(NSFC)', '中国科学技术大学', '国家级', 65.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["中国科学技术大学", "中山大学"]',
  2018, '2018-01-01', '2018-01-01 至 2021-12-31',
  '陈韵岱',
  '["陈韵岱", "黄晓", "刘洋"]',
  '["知识图谱", "数据融合", "主题43"]',
  '假数据摘要：项目 fake-zh-proj-043 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-043',
  NOW()
),
(
  'fake-zh-proj-044', 'FZ62471044', '智能芯片设计自动化关键技术（样例044）',
  '国家自然科学基金(NSFC)', '中山大学', '国家级', 70.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["中山大学", "北京交通大学"]',
  2019, '2019-01-01', '2019-01-01 至 2022-12-31',
  '黄晓',
  '["黄晓", "刘洋", "吴涛"]',
  '["知识图谱", "数据融合", "主题44"]',
  '假数据摘要：项目 fake-zh-proj-044 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-044',
  NOW()
),
(
  'fake-zh-proj-045', 'FZ62471045', '量子通信网络路由与密钥分发协议（样例045）',
  '国家自然科学基金(NSFC)', '北京交通大学', '国家级', 75.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["北京交通大学", "中国科学院计算技术研究所"]',
  2020, '2020-01-01', '2020-01-01 至 2023-12-31',
  '刘洋',
  '["刘洋", "吴涛", "马超"]',
  '["知识图谱", "数据融合", "主题45"]',
  '假数据摘要：项目 fake-zh-proj-045 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-045',
  NOW()
),
(
  'fake-zh-proj-046', 'FZ62471046', '海洋遥感多源数据同化与预报（样例046）',
  '国家自然科学基金(NSFC)', '中国科学院计算技术研究所', '国家级', 80.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["中国科学院计算技术研究所", "复旦大学"]',
  2021, '2021-01-01', '2021-01-01 至 2024-12-31',
  '吴涛',
  '["吴涛", "马超", "何静"]',
  '["知识图谱", "数据融合", "主题46"]',
  '假数据摘要：项目 fake-zh-proj-046 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-046',
  NOW()
),
(
  'fake-zh-proj-047', 'FZ62471047', '新型锂离子电池固态电解质材料（样例047）',
  '国家自然科学基金(NSFC)', '复旦大学', '国家级', 85.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["复旦大学", "上海交通大学"]',
  2022, '2022-01-01', '2022-01-01 至 2025-12-31',
  '马超',
  '["马超", "何静", "李娜"]',
  '["知识图谱", "数据融合", "主题47"]',
  '假数据摘要：项目 fake-zh-proj-047 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-047',
  NOW()
),
(
  'fake-zh-proj-048', 'FZ62471048', '城市交通数字孪生与拥堵预测（样例048）',
  '国家自然科学基金(NSFC)', '上海交通大学', '国家级', 90.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["上海交通大学", "浙江大学"]',
  2023, '2023-01-01', '2023-01-01 至 2026-12-31',
  '何静',
  '["何静", "李娜", "赵敏"]',
  '["知识图谱", "数据融合", "主题48"]',
  '假数据摘要：项目 fake-zh-proj-048 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-048',
  NOW()
),
(
  'fake-zh-proj-049', 'FZ62471049', '大模型驱动的科技情报抽取与推理（样例049）',
  '国家自然科学基金(NSFC)', '浙江大学', '国家级', 95.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["浙江大学", "南京大学"]',
  2024, '2024-01-01', '2024-01-01 至 2027-12-31',
  '李娜',
  '["李娜", "赵敏", "周杰"]',
  '["知识图谱", "数据融合", "主题49"]',
  '假数据摘要：项目 fake-zh-proj-049 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-049',
  NOW()
),
(
  'fake-zh-proj-050', 'FZ62471050', '工业互联网边缘协同调度优化（样例050）',
  '国家自然科学基金(NSFC)', '南京大学', '国家级', 100.00,
  '信息科学-计算机科学', 'F-F02', '面上项目', '北京市',
  '["南京大学", "清华大学"]',
  2018, '2018-01-01', '2018-01-01 至 2021-12-31',
  '赵敏',
  '["赵敏", "周杰", "林芳"]',
  '["知识图谱", "数据融合", "主题50"]',
  '假数据摘要：项目 fake-zh-proj-050 用于入图联调。',
  NULL,
  'https://example.com/fake-zh-proj-050',
  NOW()
);

INSERT INTO dwd_zh_project_output (
  id, total_outputs, journal_articles_count, conference_papers_count,
  degree_papers_count, patents_count, books_count, awards_count, reports_count,
  other_outputs_count, output_journal_articles, output_patents,
  output_conference_papers, output_degree_papers, output_books, output_awards,
  output_reports, output_other, updated_time
) VALUES
(
  'fake-zh-proj-001', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-001", "authors": ["张伟"], "journal": "计算机学报", "doi": "10.fake/zh.001", "year": 2021}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-002', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-002", "authors": ["王岩飞"], "journal": "计算机学报", "doi": "10.fake/zh.002", "year": 2022}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-003', 2, 1, NULL, NULL, 1,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-003", "authors": ["陈韵岱"], "journal": "计算机学报", "doi": "10.fake/zh.003", "year": 2023}]', '[{"patent_title": "假专利-fake-zh-proj-003", "patent_number": "CN202400000003.X", "patent_inventor": ["陈韵岱"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-004', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-004", "authors": ["黄晓"], "journal": "计算机学报", "doi": "10.fake/zh.004", "year": 2024}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-005', 0, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-006', 2, 1, NULL, NULL, 1,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-006", "authors": ["吴涛"], "journal": "计算机学报", "doi": "10.fake/zh.006", "year": 2020}]', '[{"patent_title": "假专利-fake-zh-proj-006", "patent_number": "CN202400000006.X", "patent_inventor": ["吴涛"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-007', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-007", "authors": ["马超"], "journal": "计算机学报", "doi": "10.fake/zh.007", "year": 2021}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-008', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-008", "authors": ["何静"], "journal": "计算机学报", "doi": "10.fake/zh.008", "year": 2022}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-009', 2, 1, NULL, NULL, 1,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-009", "authors": ["李娜"], "journal": "计算机学报", "doi": "10.fake/zh.009", "year": 2023}]', '[{"patent_title": "假专利-fake-zh-proj-009", "patent_number": "CN202400000009.X", "patent_inventor": ["李娜"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-010', 0, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-011', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-011", "authors": ["周杰"], "journal": "计算机学报", "doi": "10.fake/zh.011", "year": 2025}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-012', 2, 1, NULL, NULL, 1,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-012", "authors": ["林芳"], "journal": "计算机学报", "doi": "10.fake/zh.012", "year": 2020}]', '[{"patent_title": "假专利-fake-zh-proj-012", "patent_number": "CN202400000012.X", "patent_inventor": ["林芳"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-013', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-013", "authors": ["孙婷"], "journal": "计算机学报", "doi": "10.fake/zh.013", "year": 2021}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-014', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-014", "authors": ["郑磊"], "journal": "计算机学报", "doi": "10.fake/zh.014", "year": 2022}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-015', 1, NULL, NULL, NULL, 1,
  NULL, NULL, NULL, NULL,
  NULL, '[{"patent_title": "假专利-fake-zh-proj-015", "patent_number": "CN202400000015.X", "patent_inventor": ["徐静"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-016', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-016", "authors": ["曹磊"], "journal": "计算机学报", "doi": "10.fake/zh.016", "year": 2024}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-017', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-017", "authors": ["丁一"], "journal": "计算机学报", "doi": "10.fake/zh.017", "year": 2025}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-018', 2, 1, NULL, NULL, 1,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-018", "authors": ["韩松"], "journal": "计算机学报", "doi": "10.fake/zh.018", "year": 2020}]', '[{"patent_title": "假专利-fake-zh-proj-018", "patent_number": "CN202400000018.X", "patent_inventor": ["韩松"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-019', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-019", "authors": ["郭军"], "journal": "计算机学报", "doi": "10.fake/zh.019", "year": 2021}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-020', 0, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-021', 2, 1, NULL, NULL, 1,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-021", "authors": ["张伟"], "journal": "计算机学报", "doi": "10.fake/zh.021", "year": 2023}]', '[{"patent_title": "假专利-fake-zh-proj-021", "patent_number": "CN202400000021.X", "patent_inventor": ["张伟"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-022', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-022", "authors": ["王岩飞"], "journal": "计算机学报", "doi": "10.fake/zh.022", "year": 2024}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-023', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-023", "authors": ["陈韵岱"], "journal": "计算机学报", "doi": "10.fake/zh.023", "year": 2025}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-024', 2, 1, NULL, NULL, 1,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-024", "authors": ["黄晓"], "journal": "计算机学报", "doi": "10.fake/zh.024", "year": 2020}]', '[{"patent_title": "假专利-fake-zh-proj-024", "patent_number": "CN202400000024.X", "patent_inventor": ["黄晓"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-025', 0, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-026', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-026", "authors": ["吴涛"], "journal": "计算机学报", "doi": "10.fake/zh.026", "year": 2022}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-027', 2, 1, NULL, NULL, 1,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-027", "authors": ["马超"], "journal": "计算机学报", "doi": "10.fake/zh.027", "year": 2023}]', '[{"patent_title": "假专利-fake-zh-proj-027", "patent_number": "CN202400000027.X", "patent_inventor": ["马超"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-028', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-028", "authors": ["何静"], "journal": "计算机学报", "doi": "10.fake/zh.028", "year": 2024}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-029', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-029", "authors": ["李娜"], "journal": "计算机学报", "doi": "10.fake/zh.029", "year": 2025}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-030', 1, NULL, NULL, NULL, 1,
  NULL, NULL, NULL, NULL,
  NULL, '[{"patent_title": "假专利-fake-zh-proj-030", "patent_number": "CN202400000030.X", "patent_inventor": ["赵敏"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-031', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-031", "authors": ["周杰"], "journal": "计算机学报", "doi": "10.fake/zh.031", "year": 2021}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-032', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-032", "authors": ["林芳"], "journal": "计算机学报", "doi": "10.fake/zh.032", "year": 2022}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-033', 2, 1, NULL, NULL, 1,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-033", "authors": ["孙婷"], "journal": "计算机学报", "doi": "10.fake/zh.033", "year": 2023}]', '[{"patent_title": "假专利-fake-zh-proj-033", "patent_number": "CN202400000033.X", "patent_inventor": ["孙婷"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-034', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-034", "authors": ["郑磊"], "journal": "计算机学报", "doi": "10.fake/zh.034", "year": 2024}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-035', 0, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-036', 2, 1, NULL, NULL, 1,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-036", "authors": ["曹磊"], "journal": "计算机学报", "doi": "10.fake/zh.036", "year": 2020}]', '[{"patent_title": "假专利-fake-zh-proj-036", "patent_number": "CN202400000036.X", "patent_inventor": ["曹磊"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-037', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-037", "authors": ["丁一"], "journal": "计算机学报", "doi": "10.fake/zh.037", "year": 2021}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-038', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-038", "authors": ["韩松"], "journal": "计算机学报", "doi": "10.fake/zh.038", "year": 2022}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-039', 2, 1, NULL, NULL, 1,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-039", "authors": ["郭军"], "journal": "计算机学报", "doi": "10.fake/zh.039", "year": 2023}]', '[{"patent_title": "假专利-fake-zh-proj-039", "patent_number": "CN202400000039.X", "patent_inventor": ["郭军"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-040', 0, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-041', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-041", "authors": ["张伟"], "journal": "计算机学报", "doi": "10.fake/zh.041", "year": 2025}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-042', 2, 1, NULL, NULL, 1,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-042", "authors": ["王岩飞"], "journal": "计算机学报", "doi": "10.fake/zh.042", "year": 2020}]', '[{"patent_title": "假专利-fake-zh-proj-042", "patent_number": "CN202400000042.X", "patent_inventor": ["王岩飞"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-043', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-043", "authors": ["陈韵岱"], "journal": "计算机学报", "doi": "10.fake/zh.043", "year": 2021}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-044', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-044", "authors": ["黄晓"], "journal": "计算机学报", "doi": "10.fake/zh.044", "year": 2022}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-045', 1, NULL, NULL, NULL, 1,
  NULL, NULL, NULL, NULL,
  NULL, '[{"patent_title": "假专利-fake-zh-proj-045", "patent_number": "CN202400000045.X", "patent_inventor": ["刘洋"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-046', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-046", "authors": ["吴涛"], "journal": "计算机学报", "doi": "10.fake/zh.046", "year": 2024}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-047', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-047", "authors": ["马超"], "journal": "计算机学报", "doi": "10.fake/zh.047", "year": 2025}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-048', 2, 1, NULL, NULL, 1,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-048", "authors": ["何静"], "journal": "计算机学报", "doi": "10.fake/zh.048", "year": 2020}]', '[{"patent_title": "假专利-fake-zh-proj-048", "patent_number": "CN202400000048.X", "patent_inventor": ["何静"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-049', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  '[{"title": "假论文-fake-zh-proj-049", "authors": ["李娜"], "journal": "计算机学报", "doi": "10.fake/zh.049", "year": 2021}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
),
(
  'fake-zh-proj-050', 0, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW()
);

INSERT INTO dwd_en_project (
  id, project_number, title, project_source, funded_institution, project_level,
  funded_amount, discipline, discipline_code, fund_category, funded_province,
  participating_institution, approval_year, approval_time, research_period,
  project_host, participants, keywords, abstract, final_report_abstract,
  project_page_url, updated_time
) VALUES
(
  'fake-en-proj-001', 'FE2000001', 'Knowledge Graph Fusion for Translational Research (sample 001)',
  '美国国家科学基金(NSF)', 'FLORIDA STATE UNIVERSITY', '国家级', 112345.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["FLORIDA STATE UNIVERSITY", "University of Maine"]',
  2018, '2018-02-01', '2018-02-01 至 2021-01-31',
  'Stacey S Patterson',
  '["Stacey S Patterson", "Caitlin Howell"]',
  '["knowledge graph", "AI", "topic-1"]',
  'Fake abstract for fake-en-proj-001.',
  NULL,
  'https://example.com/fake-en-proj-001',
  NOW()
),
(
  'fake-en-proj-002', 'FE2000002', 'Bioinspired Membranes for Airborne Pathogen Detection (sample 002)',
  '美国国家科学基金(NSF)', 'University of Maine', '国家级', 124690.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Maine", "Technical University of Munich"]',
  2019, '2019-02-01', '2019-02-01 至 2022-01-31',
  'Caitlin Howell',
  '["Caitlin Howell", "Anna Schmidt"]',
  '["knowledge graph", "AI", "topic-2"]',
  'Fake abstract for fake-en-proj-002.',
  NULL,
  'https://example.com/fake-en-proj-002',
  NOW()
),
(
  'fake-en-proj-003', 'FE2000003', 'Trusted AI for Scientific Discovery (sample 003)',
  '美国国家科学基金(NSF)', 'Technical University of Munich', '国家级', 137035.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["Technical University of Munich", "Stanford University"]',
  2020, '2020-02-01', '2020-02-01 至 2023-01-31',
  'Anna Schmidt',
  '["Anna Schmidt", "Emily Chen"]',
  '["knowledge graph", "AI", "topic-3"]',
  'Fake abstract for fake-en-proj-003.',
  NULL,
  'https://example.com/fake-en-proj-003',
  NOW()
),
(
  'fake-en-proj-004', 'FE2000004', 'Graph Neural Networks for Materials Discovery (sample 004)',
  '美国国家科学基金(NSF)', 'Stanford University', '国家级', 149380.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["Stanford University", "University of Cambridge"]',
  2021, '2021-02-01', '2021-02-01 至 2024-01-31',
  'Emily Chen',
  '["Emily Chen", "David Wilson"]',
  '["knowledge graph", "AI", "topic-4"]',
  'Fake abstract for fake-en-proj-004.',
  NULL,
  'https://example.com/fake-en-proj-004',
  NOW()
),
(
  'fake-en-proj-005', 'FE2000005', 'Quantum Network Protocols for Secure Communications (sample 005)',
  '美国国家科学基金(NSF)', 'University of Cambridge', '国家级', 161725.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Cambridge", "University of Tokyo"]',
  2022, '2022-02-01', '2022-02-01 至 2025-01-31',
  'David Wilson',
  '["David Wilson", "Hiroshi Tanaka"]',
  '["knowledge graph", "AI", "topic-5"]',
  'Fake abstract for fake-en-proj-005.',
  NULL,
  'https://example.com/fake-en-proj-005',
  NOW()
),
(
  'fake-en-proj-006', 'FE2000006', 'Ocean Remote Sensing Data Assimilation (sample 006)',
  '美国国家科学基金(NSF)', 'University of Tokyo', '国家级', 174070.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Tokyo", "RWTH Aachen University"]',
  2023, '2023-02-01', '2023-02-01 至 2026-01-31',
  'Hiroshi Tanaka',
  '["Hiroshi Tanaka", "Klaus Mueller"]',
  '["knowledge graph", "AI", "topic-6"]',
  'Fake abstract for fake-en-proj-006.',
  NULL,
  'https://example.com/fake-en-proj-006',
  NOW()
),
(
  'fake-en-proj-007', 'FE2000007', 'Solid-State Electrolytes for Next-Generation Batteries (sample 007)',
  '美国国家科学基金(NSF)', 'RWTH Aachen University', '国家级', 186415.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["RWTH Aachen University", "University of Melbourne"]',
  2024, '2024-02-01', '2024-02-01 至 2027-01-31',
  'Klaus Mueller',
  '["Klaus Mueller", "Olivia Parker"]',
  '["knowledge graph", "AI", "topic-7"]',
  'Fake abstract for fake-en-proj-007.',
  NULL,
  'https://example.com/fake-en-proj-007',
  NOW()
),
(
  'fake-en-proj-008', 'FE2000008', 'Digital Twins for Urban Mobility (sample 008)',
  '美国国家科学基金(NSF)', 'University of Melbourne', '国家级', 198760.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Melbourne", "MIT"]',
  2018, '2018-02-01', '2018-02-01 至 2021-01-31',
  'Olivia Parker',
  '["Olivia Parker", "Mark A Riley"]',
  '["knowledge graph", "AI", "topic-8"]',
  'Fake abstract for fake-en-proj-008.',
  NULL,
  'https://example.com/fake-en-proj-008',
  NOW()
),
(
  'fake-en-proj-009', 'FE2000009', 'Multimodal Retrieval for Scientific Literature (sample 009)',
  '美国国家科学基金(NSF)', 'MIT', '国家级', 211105.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["MIT", "University of Oxford"]',
  2019, '2019-02-01', '2019-02-01 至 2022-01-31',
  'Mark A Riley',
  '["Mark A Riley", "James Brown"]',
  '["knowledge graph", "AI", "topic-9"]',
  'Fake abstract for fake-en-proj-009.',
  NULL,
  'https://example.com/fake-en-proj-009',
  NOW()
),
(
  'fake-en-proj-010', 'FE2000010', 'Federated Learning for Biomedical Knowledge Graphs (sample 010)',
  '美国国家科学基金(NSF)', 'University of Oxford', '国家级', 223450.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Oxford", "FLORIDA STATE UNIVERSITY"]',
  2020, '2020-02-01', '2020-02-01 至 2023-01-31',
  'James Brown',
  '["James Brown", "Stacey S Patterson"]',
  '["knowledge graph", "AI", "topic-10"]',
  'Fake abstract for fake-en-proj-010.',
  NULL,
  'https://example.com/fake-en-proj-010',
  NOW()
),
(
  'fake-en-proj-011', 'FE2000011', 'Knowledge Graph Fusion for Translational Research (sample 011)',
  '美国国家科学基金(NSF)', 'FLORIDA STATE UNIVERSITY', '国家级', 235795.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["FLORIDA STATE UNIVERSITY", "University of Maine"]',
  2021, '2021-02-01', '2021-02-01 至 2024-01-31',
  'Stacey S Patterson',
  '["Stacey S Patterson", "Caitlin Howell"]',
  '["knowledge graph", "AI", "topic-11"]',
  'Fake abstract for fake-en-proj-011.',
  NULL,
  'https://example.com/fake-en-proj-011',
  NOW()
),
(
  'fake-en-proj-012', 'FE2000012', 'Bioinspired Membranes for Airborne Pathogen Detection (sample 012)',
  '美国国家科学基金(NSF)', 'University of Maine', '国家级', 248140.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Maine", "Technical University of Munich"]',
  2022, '2022-02-01', '2022-02-01 至 2025-01-31',
  'Caitlin Howell',
  '["Caitlin Howell", "Anna Schmidt"]',
  '["knowledge graph", "AI", "topic-12"]',
  'Fake abstract for fake-en-proj-012.',
  NULL,
  'https://example.com/fake-en-proj-012',
  NOW()
),
(
  'fake-en-proj-013', 'FE2000013', 'Trusted AI for Scientific Discovery (sample 013)',
  '美国国家科学基金(NSF)', 'Technical University of Munich', '国家级', 260485.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["Technical University of Munich", "Stanford University"]',
  2023, '2023-02-01', '2023-02-01 至 2026-01-31',
  'Anna Schmidt',
  '["Anna Schmidt", "Emily Chen"]',
  '["knowledge graph", "AI", "topic-13"]',
  'Fake abstract for fake-en-proj-013.',
  NULL,
  'https://example.com/fake-en-proj-013',
  NOW()
),
(
  'fake-en-proj-014', 'FE2000014', 'Graph Neural Networks for Materials Discovery (sample 014)',
  '美国国家科学基金(NSF)', 'Stanford University', '国家级', 272830.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["Stanford University", "University of Cambridge"]',
  2024, '2024-02-01', '2024-02-01 至 2027-01-31',
  'Emily Chen',
  '["Emily Chen", "David Wilson"]',
  '["knowledge graph", "AI", "topic-14"]',
  'Fake abstract for fake-en-proj-014.',
  NULL,
  'https://example.com/fake-en-proj-014',
  NOW()
),
(
  'fake-en-proj-015', 'FE2000015', 'Quantum Network Protocols for Secure Communications (sample 015)',
  '美国国家科学基金(NSF)', 'University of Cambridge', '国家级', 285175.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Cambridge", "University of Tokyo"]',
  2018, '2018-02-01', '2018-02-01 至 2021-01-31',
  'David Wilson',
  '["David Wilson", "Hiroshi Tanaka"]',
  '["knowledge graph", "AI", "topic-15"]',
  'Fake abstract for fake-en-proj-015.',
  NULL,
  'https://example.com/fake-en-proj-015',
  NOW()
),
(
  'fake-en-proj-016', 'FE2000016', 'Ocean Remote Sensing Data Assimilation (sample 016)',
  '美国国家科学基金(NSF)', 'University of Tokyo', '国家级', 297520.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Tokyo", "RWTH Aachen University"]',
  2019, '2019-02-01', '2019-02-01 至 2022-01-31',
  'Hiroshi Tanaka',
  '["Hiroshi Tanaka", "Klaus Mueller"]',
  '["knowledge graph", "AI", "topic-16"]',
  'Fake abstract for fake-en-proj-016.',
  NULL,
  'https://example.com/fake-en-proj-016',
  NOW()
),
(
  'fake-en-proj-017', 'FE2000017', 'Solid-State Electrolytes for Next-Generation Batteries (sample 017)',
  '美国国家科学基金(NSF)', 'RWTH Aachen University', '国家级', 309865.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["RWTH Aachen University", "University of Melbourne"]',
  2020, '2020-02-01', '2020-02-01 至 2023-01-31',
  'Klaus Mueller',
  '["Klaus Mueller", "Olivia Parker"]',
  '["knowledge graph", "AI", "topic-17"]',
  'Fake abstract for fake-en-proj-017.',
  NULL,
  'https://example.com/fake-en-proj-017',
  NOW()
),
(
  'fake-en-proj-018', 'FE2000018', 'Digital Twins for Urban Mobility (sample 018)',
  '美国国家科学基金(NSF)', 'University of Melbourne', '国家级', 322210.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Melbourne", "MIT"]',
  2021, '2021-02-01', '2021-02-01 至 2024-01-31',
  'Olivia Parker',
  '["Olivia Parker", "Mark A Riley"]',
  '["knowledge graph", "AI", "topic-18"]',
  'Fake abstract for fake-en-proj-018.',
  NULL,
  'https://example.com/fake-en-proj-018',
  NOW()
),
(
  'fake-en-proj-019', 'FE2000019', 'Multimodal Retrieval for Scientific Literature (sample 019)',
  '美国国家科学基金(NSF)', 'MIT', '国家级', 334555.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["MIT", "University of Oxford"]',
  2022, '2022-02-01', '2022-02-01 至 2025-01-31',
  'Mark A Riley',
  '["Mark A Riley", "James Brown"]',
  '["knowledge graph", "AI", "topic-19"]',
  'Fake abstract for fake-en-proj-019.',
  NULL,
  'https://example.com/fake-en-proj-019',
  NOW()
),
(
  'fake-en-proj-020', 'FE2000020', 'Federated Learning for Biomedical Knowledge Graphs (sample 020)',
  '美国国家科学基金(NSF)', 'University of Oxford', '国家级', 346900.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Oxford", "FLORIDA STATE UNIVERSITY"]',
  2023, '2023-02-01', '2023-02-01 至 2026-01-31',
  'James Brown',
  '["James Brown", "Stacey S Patterson"]',
  '["knowledge graph", "AI", "topic-20"]',
  'Fake abstract for fake-en-proj-020.',
  NULL,
  'https://example.com/fake-en-proj-020',
  NOW()
),
(
  'fake-en-proj-021', 'FE2000021', 'Knowledge Graph Fusion for Translational Research (sample 021)',
  '美国国家科学基金(NSF)', 'FLORIDA STATE UNIVERSITY', '国家级', 359245.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["FLORIDA STATE UNIVERSITY", "University of Maine"]',
  2024, '2024-02-01', '2024-02-01 至 2027-01-31',
  'Stacey S Patterson',
  '["Stacey S Patterson", "Caitlin Howell"]',
  '["knowledge graph", "AI", "topic-21"]',
  'Fake abstract for fake-en-proj-021.',
  NULL,
  'https://example.com/fake-en-proj-021',
  NOW()
),
(
  'fake-en-proj-022', 'FE2000022', 'Bioinspired Membranes for Airborne Pathogen Detection (sample 022)',
  '美国国家科学基金(NSF)', 'University of Maine', '国家级', 371590.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Maine", "Technical University of Munich"]',
  2018, '2018-02-01', '2018-02-01 至 2021-01-31',
  'Caitlin Howell',
  '["Caitlin Howell", "Anna Schmidt"]',
  '["knowledge graph", "AI", "topic-22"]',
  'Fake abstract for fake-en-proj-022.',
  NULL,
  'https://example.com/fake-en-proj-022',
  NOW()
),
(
  'fake-en-proj-023', 'FE2000023', 'Trusted AI for Scientific Discovery (sample 023)',
  '美国国家科学基金(NSF)', 'Technical University of Munich', '国家级', 383935.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["Technical University of Munich", "Stanford University"]',
  2019, '2019-02-01', '2019-02-01 至 2022-01-31',
  'Anna Schmidt',
  '["Anna Schmidt", "Emily Chen"]',
  '["knowledge graph", "AI", "topic-23"]',
  'Fake abstract for fake-en-proj-023.',
  NULL,
  'https://example.com/fake-en-proj-023',
  NOW()
),
(
  'fake-en-proj-024', 'FE2000024', 'Graph Neural Networks for Materials Discovery (sample 024)',
  '美国国家科学基金(NSF)', 'Stanford University', '国家级', 396280.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["Stanford University", "University of Cambridge"]',
  2020, '2020-02-01', '2020-02-01 至 2023-01-31',
  'Emily Chen',
  '["Emily Chen", "David Wilson"]',
  '["knowledge graph", "AI", "topic-24"]',
  'Fake abstract for fake-en-proj-024.',
  NULL,
  'https://example.com/fake-en-proj-024',
  NOW()
),
(
  'fake-en-proj-025', 'FE2000025', 'Quantum Network Protocols for Secure Communications (sample 025)',
  '美国国家科学基金(NSF)', 'University of Cambridge', '国家级', 408625.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Cambridge", "University of Tokyo"]',
  2021, '2021-02-01', '2021-02-01 至 2024-01-31',
  'David Wilson',
  '["David Wilson", "Hiroshi Tanaka"]',
  '["knowledge graph", "AI", "topic-25"]',
  'Fake abstract for fake-en-proj-025.',
  NULL,
  'https://example.com/fake-en-proj-025',
  NOW()
),
(
  'fake-en-proj-026', 'FE2000026', 'Ocean Remote Sensing Data Assimilation (sample 026)',
  '美国国家科学基金(NSF)', 'University of Tokyo', '国家级', 420970.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Tokyo", "RWTH Aachen University"]',
  2022, '2022-02-01', '2022-02-01 至 2025-01-31',
  'Hiroshi Tanaka',
  '["Hiroshi Tanaka", "Klaus Mueller"]',
  '["knowledge graph", "AI", "topic-26"]',
  'Fake abstract for fake-en-proj-026.',
  NULL,
  'https://example.com/fake-en-proj-026',
  NOW()
),
(
  'fake-en-proj-027', 'FE2000027', 'Solid-State Electrolytes for Next-Generation Batteries (sample 027)',
  '美国国家科学基金(NSF)', 'RWTH Aachen University', '国家级', 433315.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["RWTH Aachen University", "University of Melbourne"]',
  2023, '2023-02-01', '2023-02-01 至 2026-01-31',
  'Klaus Mueller',
  '["Klaus Mueller", "Olivia Parker"]',
  '["knowledge graph", "AI", "topic-27"]',
  'Fake abstract for fake-en-proj-027.',
  NULL,
  'https://example.com/fake-en-proj-027',
  NOW()
),
(
  'fake-en-proj-028', 'FE2000028', 'Digital Twins for Urban Mobility (sample 028)',
  '美国国家科学基金(NSF)', 'University of Melbourne', '国家级', 445660.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Melbourne", "MIT"]',
  2024, '2024-02-01', '2024-02-01 至 2027-01-31',
  'Olivia Parker',
  '["Olivia Parker", "Mark A Riley"]',
  '["knowledge graph", "AI", "topic-28"]',
  'Fake abstract for fake-en-proj-028.',
  NULL,
  'https://example.com/fake-en-proj-028',
  NOW()
),
(
  'fake-en-proj-029', 'FE2000029', 'Multimodal Retrieval for Scientific Literature (sample 029)',
  '美国国家科学基金(NSF)', 'MIT', '国家级', 458005.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["MIT", "University of Oxford"]',
  2018, '2018-02-01', '2018-02-01 至 2021-01-31',
  'Mark A Riley',
  '["Mark A Riley", "James Brown"]',
  '["knowledge graph", "AI", "topic-29"]',
  'Fake abstract for fake-en-proj-029.',
  NULL,
  'https://example.com/fake-en-proj-029',
  NOW()
),
(
  'fake-en-proj-030', 'FE2000030', 'Federated Learning for Biomedical Knowledge Graphs (sample 030)',
  '美国国家科学基金(NSF)', 'University of Oxford', '国家级', 470350.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Oxford", "FLORIDA STATE UNIVERSITY"]',
  2019, '2019-02-01', '2019-02-01 至 2022-01-31',
  'James Brown',
  '["James Brown", "Stacey S Patterson"]',
  '["knowledge graph", "AI", "topic-30"]',
  'Fake abstract for fake-en-proj-030.',
  NULL,
  'https://example.com/fake-en-proj-030',
  NOW()
),
(
  'fake-en-proj-031', 'FE2000031', 'Knowledge Graph Fusion for Translational Research (sample 031)',
  '美国国家科学基金(NSF)', 'FLORIDA STATE UNIVERSITY', '国家级', 482695.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["FLORIDA STATE UNIVERSITY", "University of Maine"]',
  2020, '2020-02-01', '2020-02-01 至 2023-01-31',
  'Stacey S Patterson',
  '["Stacey S Patterson", "Caitlin Howell"]',
  '["knowledge graph", "AI", "topic-31"]',
  'Fake abstract for fake-en-proj-031.',
  NULL,
  'https://example.com/fake-en-proj-031',
  NOW()
),
(
  'fake-en-proj-032', 'FE2000032', 'Bioinspired Membranes for Airborne Pathogen Detection (sample 032)',
  '美国国家科学基金(NSF)', 'University of Maine', '国家级', 495040.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Maine", "Technical University of Munich"]',
  2021, '2021-02-01', '2021-02-01 至 2024-01-31',
  'Caitlin Howell',
  '["Caitlin Howell", "Anna Schmidt"]',
  '["knowledge graph", "AI", "topic-32"]',
  'Fake abstract for fake-en-proj-032.',
  NULL,
  'https://example.com/fake-en-proj-032',
  NOW()
),
(
  'fake-en-proj-033', 'FE2000033', 'Trusted AI for Scientific Discovery (sample 033)',
  '美国国家科学基金(NSF)', 'Technical University of Munich', '国家级', 507385.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["Technical University of Munich", "Stanford University"]',
  2022, '2022-02-01', '2022-02-01 至 2025-01-31',
  'Anna Schmidt',
  '["Anna Schmidt", "Emily Chen"]',
  '["knowledge graph", "AI", "topic-33"]',
  'Fake abstract for fake-en-proj-033.',
  NULL,
  'https://example.com/fake-en-proj-033',
  NOW()
),
(
  'fake-en-proj-034', 'FE2000034', 'Graph Neural Networks for Materials Discovery (sample 034)',
  '美国国家科学基金(NSF)', 'Stanford University', '国家级', 519730.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["Stanford University", "University of Cambridge"]',
  2023, '2023-02-01', '2023-02-01 至 2026-01-31',
  'Emily Chen',
  '["Emily Chen", "David Wilson"]',
  '["knowledge graph", "AI", "topic-34"]',
  'Fake abstract for fake-en-proj-034.',
  NULL,
  'https://example.com/fake-en-proj-034',
  NOW()
),
(
  'fake-en-proj-035', 'FE2000035', 'Quantum Network Protocols for Secure Communications (sample 035)',
  '美国国家科学基金(NSF)', 'University of Cambridge', '国家级', 532075.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Cambridge", "University of Tokyo"]',
  2024, '2024-02-01', '2024-02-01 至 2027-01-31',
  'David Wilson',
  '["David Wilson", "Hiroshi Tanaka"]',
  '["knowledge graph", "AI", "topic-35"]',
  'Fake abstract for fake-en-proj-035.',
  NULL,
  'https://example.com/fake-en-proj-035',
  NOW()
),
(
  'fake-en-proj-036', 'FE2000036', 'Ocean Remote Sensing Data Assimilation (sample 036)',
  '美国国家科学基金(NSF)', 'University of Tokyo', '国家级', 544420.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Tokyo", "RWTH Aachen University"]',
  2018, '2018-02-01', '2018-02-01 至 2021-01-31',
  'Hiroshi Tanaka',
  '["Hiroshi Tanaka", "Klaus Mueller"]',
  '["knowledge graph", "AI", "topic-36"]',
  'Fake abstract for fake-en-proj-036.',
  NULL,
  'https://example.com/fake-en-proj-036',
  NOW()
),
(
  'fake-en-proj-037', 'FE2000037', 'Solid-State Electrolytes for Next-Generation Batteries (sample 037)',
  '美国国家科学基金(NSF)', 'RWTH Aachen University', '国家级', 556765.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["RWTH Aachen University", "University of Melbourne"]',
  2019, '2019-02-01', '2019-02-01 至 2022-01-31',
  'Klaus Mueller',
  '["Klaus Mueller", "Olivia Parker"]',
  '["knowledge graph", "AI", "topic-37"]',
  'Fake abstract for fake-en-proj-037.',
  NULL,
  'https://example.com/fake-en-proj-037',
  NOW()
),
(
  'fake-en-proj-038', 'FE2000038', 'Digital Twins for Urban Mobility (sample 038)',
  '美国国家科学基金(NSF)', 'University of Melbourne', '国家级', 569110.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Melbourne", "MIT"]',
  2020, '2020-02-01', '2020-02-01 至 2023-01-31',
  'Olivia Parker',
  '["Olivia Parker", "Mark A Riley"]',
  '["knowledge graph", "AI", "topic-38"]',
  'Fake abstract for fake-en-proj-038.',
  NULL,
  'https://example.com/fake-en-proj-038',
  NOW()
),
(
  'fake-en-proj-039', 'FE2000039', 'Multimodal Retrieval for Scientific Literature (sample 039)',
  '美国国家科学基金(NSF)', 'MIT', '国家级', 581455.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["MIT", "University of Oxford"]',
  2021, '2021-02-01', '2021-02-01 至 2024-01-31',
  'Mark A Riley',
  '["Mark A Riley", "James Brown"]',
  '["knowledge graph", "AI", "topic-39"]',
  'Fake abstract for fake-en-proj-039.',
  NULL,
  'https://example.com/fake-en-proj-039',
  NOW()
),
(
  'fake-en-proj-040', 'FE2000040', 'Federated Learning for Biomedical Knowledge Graphs (sample 040)',
  '美国国家科学基金(NSF)', 'University of Oxford', '国家级', 593800.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Oxford", "FLORIDA STATE UNIVERSITY"]',
  2022, '2022-02-01', '2022-02-01 至 2025-01-31',
  'James Brown',
  '["James Brown", "Stacey S Patterson"]',
  '["knowledge graph", "AI", "topic-40"]',
  'Fake abstract for fake-en-proj-040.',
  NULL,
  'https://example.com/fake-en-proj-040',
  NOW()
),
(
  'fake-en-proj-041', 'FE2000041', 'Knowledge Graph Fusion for Translational Research (sample 041)',
  '美国国家科学基金(NSF)', 'FLORIDA STATE UNIVERSITY', '国家级', 606145.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["FLORIDA STATE UNIVERSITY", "University of Maine"]',
  2023, '2023-02-01', '2023-02-01 至 2026-01-31',
  'Stacey S Patterson',
  '["Stacey S Patterson", "Caitlin Howell"]',
  '["knowledge graph", "AI", "topic-41"]',
  'Fake abstract for fake-en-proj-041.',
  NULL,
  'https://example.com/fake-en-proj-041',
  NOW()
),
(
  'fake-en-proj-042', 'FE2000042', 'Bioinspired Membranes for Airborne Pathogen Detection (sample 042)',
  '美国国家科学基金(NSF)', 'University of Maine', '国家级', 618490.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Maine", "Technical University of Munich"]',
  2024, '2024-02-01', '2024-02-01 至 2027-01-31',
  'Caitlin Howell',
  '["Caitlin Howell", "Anna Schmidt"]',
  '["knowledge graph", "AI", "topic-42"]',
  'Fake abstract for fake-en-proj-042.',
  NULL,
  'https://example.com/fake-en-proj-042',
  NOW()
),
(
  'fake-en-proj-043', 'FE2000043', 'Trusted AI for Scientific Discovery (sample 043)',
  '美国国家科学基金(NSF)', 'Technical University of Munich', '国家级', 630835.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["Technical University of Munich", "Stanford University"]',
  2018, '2018-02-01', '2018-02-01 至 2021-01-31',
  'Anna Schmidt',
  '["Anna Schmidt", "Emily Chen"]',
  '["knowledge graph", "AI", "topic-43"]',
  'Fake abstract for fake-en-proj-043.',
  NULL,
  'https://example.com/fake-en-proj-043',
  NOW()
),
(
  'fake-en-proj-044', 'FE2000044', 'Graph Neural Networks for Materials Discovery (sample 044)',
  '美国国家科学基金(NSF)', 'Stanford University', '国家级', 643180.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["Stanford University", "University of Cambridge"]',
  2019, '2019-02-01', '2019-02-01 至 2022-01-31',
  'Emily Chen',
  '["Emily Chen", "David Wilson"]',
  '["knowledge graph", "AI", "topic-44"]',
  'Fake abstract for fake-en-proj-044.',
  NULL,
  'https://example.com/fake-en-proj-044',
  NOW()
),
(
  'fake-en-proj-045', 'FE2000045', 'Quantum Network Protocols for Secure Communications (sample 045)',
  '美国国家科学基金(NSF)', 'University of Cambridge', '国家级', 655525.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Cambridge", "University of Tokyo"]',
  2020, '2020-02-01', '2020-02-01 至 2023-01-31',
  'David Wilson',
  '["David Wilson", "Hiroshi Tanaka"]',
  '["knowledge graph", "AI", "topic-45"]',
  'Fake abstract for fake-en-proj-045.',
  NULL,
  'https://example.com/fake-en-proj-045',
  NOW()
),
(
  'fake-en-proj-046', 'FE2000046', 'Ocean Remote Sensing Data Assimilation (sample 046)',
  '美国国家科学基金(NSF)', 'University of Tokyo', '国家级', 667870.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Tokyo", "RWTH Aachen University"]',
  2021, '2021-02-01', '2021-02-01 至 2024-01-31',
  'Hiroshi Tanaka',
  '["Hiroshi Tanaka", "Klaus Mueller"]',
  '["knowledge graph", "AI", "topic-46"]',
  'Fake abstract for fake-en-proj-046.',
  NULL,
  'https://example.com/fake-en-proj-046',
  NOW()
),
(
  'fake-en-proj-047', 'FE2000047', 'Solid-State Electrolytes for Next-Generation Batteries (sample 047)',
  '美国国家科学基金(NSF)', 'RWTH Aachen University', '国家级', 680215.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["RWTH Aachen University", "University of Melbourne"]',
  2022, '2022-02-01', '2022-02-01 至 2025-01-31',
  'Klaus Mueller',
  '["Klaus Mueller", "Olivia Parker"]',
  '["knowledge graph", "AI", "topic-47"]',
  'Fake abstract for fake-en-proj-047.',
  NULL,
  'https://example.com/fake-en-proj-047',
  NOW()
),
(
  'fake-en-proj-048', 'FE2000048', 'Digital Twins for Urban Mobility (sample 048)',
  '美国国家科学基金(NSF)', 'University of Melbourne', '国家级', 692560.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Melbourne", "MIT"]',
  2023, '2023-02-01', '2023-02-01 至 2026-01-31',
  'Olivia Parker',
  '["Olivia Parker", "Mark A Riley"]',
  '["knowledge graph", "AI", "topic-48"]',
  'Fake abstract for fake-en-proj-048.',
  NULL,
  'https://example.com/fake-en-proj-048',
  NOW()
),
(
  'fake-en-proj-049', 'FE2000049', 'Multimodal Retrieval for Scientific Literature (sample 049)',
  '美国国家科学基金(NSF)', 'MIT', '国家级', 704905.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["MIT", "University of Oxford"]',
  2024, '2024-02-01', '2024-02-01 至 2027-01-31',
  'Mark A Riley',
  '["Mark A Riley", "James Brown"]',
  '["knowledge graph", "AI", "topic-49"]',
  'Fake abstract for fake-en-proj-049.',
  NULL,
  'https://example.com/fake-en-proj-049',
  NOW()
),
(
  'fake-en-proj-050', 'FE2000050', 'Federated Learning for Biomedical Knowledge Graphs (sample 050)',
  '美国国家科学基金(NSF)', 'University of Oxford', '国家级', 717250.00,
  NULL, NULL, 'Standard Grant', NULL,
  '["University of Oxford", "FLORIDA STATE UNIVERSITY"]',
  2018, '2018-02-01', '2018-02-01 至 2021-01-31',
  'James Brown',
  '["James Brown", "Stacey S Patterson"]',
  '["knowledge graph", "AI", "topic-50"]',
  'Fake abstract for fake-en-proj-050.',
  NULL,
  'https://example.com/fake-en-proj-050',
  NOW()
);

INSERT INTO dwd_en_project_output (
  id, total_outputs, journal_articles_count, conference_papers_count,
  degree_papers_count, patents_count, clinical_trials_count, books_count,
  awards_count, reports_count, other_outputs_count,
  output_journal_articles, output_patents, output_conference_papers,
  output_degree_papers, output_clinical_trials, output_books, output_awards,
  output_reports, output_other
) VALUES
(
  'fake-en-proj-001', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-001", "authors": ["Stacey S Patterson"], "journal": "Nature Communications", "doi": "10.fake/en.001", "year": 2022}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-002', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-002", "authors": ["Caitlin Howell"], "journal": "Nature Communications", "doi": "10.fake/en.002", "year": 2023}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-003', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-003", "authors": ["Anna Schmidt"], "journal": "Nature Communications", "doi": "10.fake/en.003", "year": 2024}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-004', 0, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-005', 2, 1, NULL, NULL, 1,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-005", "authors": ["David Wilson"], "journal": "Nature Communications", "doi": "10.fake/en.005", "year": 2021}]', '[{"patent_title": "Fake patent fake-en-proj-005", "patent_number": "US20240000005A1", "patent_inventor": ["David Wilson"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-006', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-006", "authors": ["Hiroshi Tanaka"], "journal": "Nature Communications", "doi": "10.fake/en.006", "year": 2022}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-007', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-007", "authors": ["Klaus Mueller"], "journal": "Nature Communications", "doi": "10.fake/en.007", "year": 2023}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-008', 0, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-009', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-009", "authors": ["Mark A Riley"], "journal": "Nature Communications", "doi": "10.fake/en.009", "year": 2025}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-010', 2, 1, NULL, NULL, 1,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-010", "authors": ["James Brown"], "journal": "Nature Communications", "doi": "10.fake/en.010", "year": 2021}]', '[{"patent_title": "Fake patent fake-en-proj-010", "patent_number": "US20240000010A1", "patent_inventor": ["James Brown"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-011', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-011", "authors": ["Stacey S Patterson"], "journal": "Nature Communications", "doi": "10.fake/en.011", "year": 2022}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-012', 0, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-013', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-013", "authors": ["Anna Schmidt"], "journal": "Nature Communications", "doi": "10.fake/en.013", "year": 2024}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-014', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-014", "authors": ["Emily Chen"], "journal": "Nature Communications", "doi": "10.fake/en.014", "year": 2025}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-015', 2, 1, NULL, NULL, 1,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-015", "authors": ["David Wilson"], "journal": "Nature Communications", "doi": "10.fake/en.015", "year": 2021}]', '[{"patent_title": "Fake patent fake-en-proj-015", "patent_number": "US20240000015A1", "patent_inventor": ["David Wilson"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-016', 0, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-017', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-017", "authors": ["Klaus Mueller"], "journal": "Nature Communications", "doi": "10.fake/en.017", "year": 2023}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-018', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-018", "authors": ["Olivia Parker"], "journal": "Nature Communications", "doi": "10.fake/en.018", "year": 2024}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-019', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-019", "authors": ["Mark A Riley"], "journal": "Nature Communications", "doi": "10.fake/en.019", "year": 2025}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-020', 1, NULL, NULL, NULL, 1,
  NULL, NULL, NULL, NULL, NULL,
  NULL, '[{"patent_title": "Fake patent fake-en-proj-020", "patent_number": "US20240000020A1", "patent_inventor": ["James Brown"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-021', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-021", "authors": ["Stacey S Patterson"], "journal": "Nature Communications", "doi": "10.fake/en.021", "year": 2022}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-022', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-022", "authors": ["Caitlin Howell"], "journal": "Nature Communications", "doi": "10.fake/en.022", "year": 2023}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-023', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-023", "authors": ["Anna Schmidt"], "journal": "Nature Communications", "doi": "10.fake/en.023", "year": 2024}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-024', 0, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-025', 2, 1, NULL, NULL, 1,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-025", "authors": ["David Wilson"], "journal": "Nature Communications", "doi": "10.fake/en.025", "year": 2021}]', '[{"patent_title": "Fake patent fake-en-proj-025", "patent_number": "US20240000025A1", "patent_inventor": ["David Wilson"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-026', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-026", "authors": ["Hiroshi Tanaka"], "journal": "Nature Communications", "doi": "10.fake/en.026", "year": 2022}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-027', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-027", "authors": ["Klaus Mueller"], "journal": "Nature Communications", "doi": "10.fake/en.027", "year": 2023}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-028', 0, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-029', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-029", "authors": ["Mark A Riley"], "journal": "Nature Communications", "doi": "10.fake/en.029", "year": 2025}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-030', 2, 1, NULL, NULL, 1,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-030", "authors": ["James Brown"], "journal": "Nature Communications", "doi": "10.fake/en.030", "year": 2021}]', '[{"patent_title": "Fake patent fake-en-proj-030", "patent_number": "US20240000030A1", "patent_inventor": ["James Brown"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-031', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-031", "authors": ["Stacey S Patterson"], "journal": "Nature Communications", "doi": "10.fake/en.031", "year": 2022}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-032', 0, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-033', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-033", "authors": ["Anna Schmidt"], "journal": "Nature Communications", "doi": "10.fake/en.033", "year": 2024}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-034', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-034", "authors": ["Emily Chen"], "journal": "Nature Communications", "doi": "10.fake/en.034", "year": 2025}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-035', 2, 1, NULL, NULL, 1,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-035", "authors": ["David Wilson"], "journal": "Nature Communications", "doi": "10.fake/en.035", "year": 2021}]', '[{"patent_title": "Fake patent fake-en-proj-035", "patent_number": "US20240000035A1", "patent_inventor": ["David Wilson"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-036', 0, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-037', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-037", "authors": ["Klaus Mueller"], "journal": "Nature Communications", "doi": "10.fake/en.037", "year": 2023}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-038', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-038", "authors": ["Olivia Parker"], "journal": "Nature Communications", "doi": "10.fake/en.038", "year": 2024}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-039', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-039", "authors": ["Mark A Riley"], "journal": "Nature Communications", "doi": "10.fake/en.039", "year": 2025}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-040', 1, NULL, NULL, NULL, 1,
  NULL, NULL, NULL, NULL, NULL,
  NULL, '[{"patent_title": "Fake patent fake-en-proj-040", "patent_number": "US20240000040A1", "patent_inventor": ["James Brown"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-041', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-041", "authors": ["Stacey S Patterson"], "journal": "Nature Communications", "doi": "10.fake/en.041", "year": 2022}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-042', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-042", "authors": ["Caitlin Howell"], "journal": "Nature Communications", "doi": "10.fake/en.042", "year": 2023}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-043', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-043", "authors": ["Anna Schmidt"], "journal": "Nature Communications", "doi": "10.fake/en.043", "year": 2024}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-044', 0, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-045', 2, 1, NULL, NULL, 1,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-045", "authors": ["David Wilson"], "journal": "Nature Communications", "doi": "10.fake/en.045", "year": 2021}]', '[{"patent_title": "Fake patent fake-en-proj-045", "patent_number": "US20240000045A1", "patent_inventor": ["David Wilson"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-046', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-046", "authors": ["Hiroshi Tanaka"], "journal": "Nature Communications", "doi": "10.fake/en.046", "year": 2022}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-047', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-047", "authors": ["Klaus Mueller"], "journal": "Nature Communications", "doi": "10.fake/en.047", "year": 2023}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-048', 0, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-049', 1, 1, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-049", "authors": ["Mark A Riley"], "journal": "Nature Communications", "doi": "10.fake/en.049", "year": 2025}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
),
(
  'fake-en-proj-050', 2, 1, NULL, NULL, 1,
  NULL, NULL, NULL, NULL, NULL,
  '[{"title": "Fake paper fake-en-proj-050", "authors": ["James Brown"], "journal": "Nature Communications", "doi": "10.fake/en.050", "year": 2021}]', '[{"patent_title": "Fake patent fake-en-proj-050", "patent_number": "US20240000050A1", "patent_inventor": ["James Brown"]}]', NULL, NULL, NULL, NULL, NULL, NULL, NULL
);

