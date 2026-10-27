# dp_gkx 图空间·九大业务可命中测试数据清单（2026-10-27 实跑验证）

- 图空间： trsgraph `dp_gkx`（Person 19 万 / Paper 74 万 / Organization 2 万 / Event 2.5 万…）
- 验证方式： dev2 容器内 ASGI 直调真实九大业务接口（请求头 `X-Business-Graph-Space: dp_gkx`），全部为查询端点，只读验证
- 注意： 该空间数据 2026-10-27 仍在持续导入更新（当日多轮边数据重灌），**数字以当日为准**；孙哲浩×沈忱共同论文由 11 篇变为 0 即为重灌所致
- 端点前缀均 `/api/v1`；输入 JSON 可直接抄用

## M1 直接关系 `kg-construction/expert-direct-relations/query`

⚠️ **不要带 startTime/endTime**： COAUTHOR_WITH 边无 relation_time 属性，一带时间窗即全被滤空（reason=empty_result）。

| 组 | 输入 | 实跑结果 |
|---|---|---|
| 1 | A=person_0209a7v6(赵刚) B=person_1S5195f4(朱保君) institution=清华大学计算机科学与技术系 | total=1，同机构+共论文，coPaperCount=18 |
| 2 | A=person_1D693hk4(梁中明) B=person_8196m452(李坚强) institution=清华大学计算机科学与技术系 | total=1，同机构+共论文，26 |
| 3 | A=person_060S790j(孙哲浩) B=person_20N32Z57(沈忱) | total=1，共论文，12 |
| 附 | A-only=person_0209a7v6 limit=5 | top5 coPaperCount 90/80/64…（列表模式可用） |

## M2 间接关系 `kg-construction/expert-indirect-relations/demo/structured-result`

| 组 | core_node_id | relation_types | 实跑 |
|---|---|---|---|
| 1 | person_0209a7v6 赵刚 | [学术关联] depth=2 minStrength=0.3 | 直接 26 / 间接 126 / 路径 147，avgStrength 0.70 |
| 2 | person_1D693hk4 梁中明 | [学术关联] depth=2 | 31 / 285 / 315，0.69 |
| 3 | person_8196m452 李坚强 | [机构关联] depth=2 | 1 / 2 / 2（机构关联小样本可用） |

## M3 合作成果 `kg-construction/expert-cooperation-achievements/query`

| 组 | 输入 | 实跑 |
|---|---|---|
| 1 | source=person_0209a7v6 target=person_1S5195f4 types=[论文] 2015-01~2026-08 | papers=18（2015 起，600-T 磁场论文等） |
| 2 | source=person_1D693hk4 target=person_8196m452 types=[全部] | papers=3 |
| 3 | source=person_5k153q31 target=person_710a42c569116e972ee82a36f227276f types=[全部] 2000-01 起 | **projects=1**（BESIII 国家级项目） |

❌ 专利/获奖两类**无对**： INVENTED_BY 55 边全为单人专利；output_awards 全空 → 结构性缺口。

## M4 同事关系 `kg-service/expert-colleague-relation`

| 组 | 输入 | 实跑 |
|---|---|---|
| 1 | a=person_0209a7v6 b=person_1S5195f4 2015-01~2026-08 | 期间成果 7，overlap 106 月 |
| 2 | a=person_1D693hk4 b=person_8196m452 | 期间成果 10，overlap 94 月 |
| 3 | a=person_c8669294(张沕琳) b=person_c9915341(向德辉) 2020-01~2024-12 | 期间成果 3，overlap 82 月（濠江測試數碼 033） |

## M5 校友关系 `kg-construction/expert-alumni-relations/query`

⚠️ 可用对集中在 9F9A00xx **演示种子人员**（真人教育背景仅约 24/19 万）；kgtest_20260721 系列教育属性乱码（mojibake）不可查。

| 组 | 输入 | 实跑 |
|---|---|---|
| 1 | 9F9A0084(顾清妍)×9F9A0096(常舒宁) 上海交通大学 博士 | 同校+同学历+同期 ✓ |
| 2 | 9F9A0092(武清歌)×9F9A0084(顾清妍) 上海交通大学 | 同校（异学历样本）✓ |
| 3 | 9F9A0098(裴诗雅)×9F9A0066(熊若兰) 北京大学 学士 | 同校+同学历+同期 ✓ |

## M6 论文合作 `kg-construction/expert-paper-cooperation-relations/structured-result`

| 组 | 输入 | 实跑 |
|---|---|---|
| 1 | A=person_1D693hk4 B=person_2y1H981f(F. Richard Yu) | 116 篇，跨机构对（清华×卡尔顿大学），impact 99.5 |
| 2 | A=person_0209a7v6 B=person_1S5195f4 | 18 篇，2015-2020，impact 99.5 |
| 3 | A=person_1D693hk4 B=person_8196m452 | 13 篇，2020-2023 |
| 附 | A=person_0209a7v6 B=person_4W4791544(Jingkun Zhao) | 90 篇 |

⚠️ citation 恒 0（被引未接入）；authorUnits 来自人员属性而非论文 affiliation。

## M7 重点企业关系 `kg-service/key-enterprise-relation`

| 组 | 输入 | 实跑 |
|---|---|---|
| 1 | person_aa21276d13af5bb7f5d03ae1ea18a3ce(舒达坤) 优鹰智能科技(深圳)有限公司 董事长 无人机系统 | L1 高管任职，tech_field 命中，风险=暂无 |
| 2 | person_224231f397fd5ee63a301ad7e82271d1 浙江大华技术股份有限公司 副总经理 云台摄像机、无人机系统 | L1，已上市企业 |
| 3 | person_116c41f92ecebd7f3f8344b11a616bef 优鹰智能科技(深圳)有限公司 董事 无人机系统 | L1 |

⚠️ 合作时间恒空（任职日期属性全空）；风险提示恒"暂无"（司法类事件未挂边）。

## M8 节点头部事件 `kg-service/industry-node-top-events`

⚠️ time_range_end **不能晚于当前月**（422 校验错）。

| 组 | 输入 | 实跑 |
|---|---|---|
| 1 | IC0007007 集成电路设计 annual_finance top_n=10 | events=10，豪威 436 亿年报 rank1，士兰微 267 亿；risk_level 中 |
| 2 | IC9901077 云台摄像机 recruit top_n=5 | events=5 全部浙江大华招聘 |
| 3 | IC9901090 民用无人机 financing top_n=5 | events=3，翔农创新 A 轮 1000 万 rank1 |

## M9 产业链全景 `kg-construction/industry-chain-panorama/query`

| 组 | 输入 | 实跑 |
|---|---|---|
| 1 | industry=集成电路 anchorId=node_IC0007004 depth=2 topK=5 | 核心技术4+领军企业5+领军专家3+产业动态2 |
| 2 | industry=低空经济 anchorId=node_IC9901036 depth=2 topK=5 | 基建设施1+企业5+专家3（李钊 H指数28）+事件0 |
| 3 | industry=集成电路 anchorId=node_IC0007007 depth=3 topK=10 | 4+10+2+3（含股权/战略融资事件） |

❌ 人工智能链 0 节点不可用。

## 结构性缺口汇总（相对远端 dev 空间）

1. M1 时间窗不可用（边无 relation_time）
2. M3 专利单人、获奖全空
3. M5 真人教育背景约 24/19 万，依赖演示种子
4. M6 被引恒 0
5. M7 合作时间空、风险提示恒暂无（司法事件悬挂无边）
6. 人工智能产业链空
7. AFFILIATED_WITH 仅 81 条，但三机构组内共同论文真实存在（M4 可用）
8. kgtest 系列教育/姓名乱码
