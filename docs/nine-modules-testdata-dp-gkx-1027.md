# dp_gkx 图空间·九大业务可命中测试数据清单（2026-10-27 实跑验证；10-28 复验并扩至每模块 5 组）

- 空间： 本机 trsgraph `dp_gkx`（Person 19 万 / Paper 74 万 / Org 2 万…）
- 验证方式： dev2 容器内 ASGI 直调（`X-Business-Graph-Space: dp_gkx`），全部查询端点，只读
- 10-28 复验结论： **27 组原文档数据 26 组仍可查**；唯一失效 = M6-1（梁中明×F.R.Yu，重灌把 F.R.Yu 重建为桩点、论文边没了，无窗也救不回）；M6 附组（赵×Jingkun Zhao）同因失效。已用新对补齐至 M6 5 组。
- 共性坑（10-27 14:20 重灌所致）： **大量共同论文的年份字段为空** → M3/M6 只要带时间窗（哪怕 1900-01 起）即全滤为 0。规避：M3 把时间字段**整体省略**（传空串会 422）；M6 传 `startTime:""`、`endTime:""`（空串=无窗）。年份仍在的对（M3-1、M6-2/4）可带窗。
- 端点前缀均 `/api/v1`；输入可直接抄用

## M1 直接关系 `kg-construction/expert-direct-relations/query`

⚠️ **不要带 startTime/endTime**： COAUTHOR_WITH 边无 relation_time 属性，一带时间窗即全被滤空（reason=empty_result）。

| 组 | 输入 | 实跑结果 |
|---|---|---|
| 1 | A=person_0209a7v6(赵刚) B=person_1S5195f4(朱保君) institution=清华大学计算机科学与技术系 | total=1，同机构+共论文，coPaperCount=18 |
| 2 | A=person_1D693hk4(梁中明) B=person_8196m452(李坚强) institution=清华大学计算机科学与技术系 | total=1，同机构+共论文，26 |
| 3 | A=person_060S790j(孙哲浩) B=person_20N32Z57(沈忱) | total=1，共论文，12 |
| 4 | A=person_uF227379(王翊) B=person_154p2738(王毅) | total=1，共论文，918（COAUTHOR_WITH 权重口径） |
| 5 | A=person_ij9647339(王祎) B=person_154p2738(王毅) | total=1，共论文，918 |
| 附 | A-only=person_0209a7v6 limit=5 | top5 cpc 90/80/64…（列表模式可用） |

## M2 间接关系 `kg-construction/expert-indirect-relations/demo/structured-result`

| 组 | core_node_id | relation_types | 实跑 |
|---|---|---|---|
| 1 | person_0209a7v6 赵刚 | [学术关联] depth2 min0.3 | 直接 26 / 间接 126 / 路径 147，avgStrength 0.70 |
| 2 | person_1D693hk4 梁中明 | [学术关联] | 31 / 285 / 315，0.69 |
| 3 | person_8196m452 李坚强 | [机构关联] | 1 / 2 / 2（机构关联小样本可用） |
| 4 | person_2y1H981f F.R.Yu | [学术关联] depth2 min0.3 | 路径 395 |
| 5 | person_uF227379 王翊 | [学术关联] depth2 min0.3 | 路径 116 |

## M3 合作成果 `kg-construction/expert-cooperation-achievements/query`

⚠️ 组 4/5 的共同论**文年份字段为空**，时间字段（timeRangeStart/End）**必须整体省略**——带任意窗口全滤 0，传空串 422。

| 组 | 输入 | 实跑 |
|---|---|---|
| 1 | source=person_0209a7v6 target=person_1S5195f4 types=[论文] 2015-01~2026-08 | papers=18（2015 起，600-T 磁场论文等） |
| 2 | source=person_1D693hk4 target=person_8196m452 types=[全部] | papers=3 |
| 3 | source=person_5k153q31 target=person_710a42c569116e972ee82a36f227276f types=[全部] 2000-01 起 | **projects=1**（BESIII 国家级项目） |
| 4 | source=person_8196m452(李坚强) target=person_21o9K09L(Qiuzhen Lin) types=[论文] 2015-01~2026-08 | papers=3（跨机构对：清华×深圳大学） |
| 5 | source=person_8196m452(李坚强) target=person_84ed6ph4(明仲) types=[全部]（**无时间字段**） | **items=17**（首条《UAV/UGV 协同系统混合路径规划》） |
| 附 | 孙哲浩×沈忱 types=[论文]（无时间字段） | items=11 |

❌ 专利/获奖两类**无对**： INVENTED_BY 55 边全为单人专利；output_awards 全空 → 结构性缺口。

## M4 同事关系 `kg-service/expert-colleague-relation`

⚠️ 匹配逻辑 = 两人 **AFFILIATED_WITH 任职边指向同一机构顶点** + 任职期交集。全图同机构且有共同论文的对仅 3 对（组 1/4/张沕琳组）；孙哲浩现任机构是北大、9F9A 演示员无此边，故不能当同事对。

| 组 | 输入 | 实跑 |
|---|---|---|
| 1 | a=person_0209a7v6 b=person_1S5195f4 2015-01~2026-08 | 期间成果 7，overlap 106 月 |
| 2 | a=person_1D693hk4 b=person_8196m452 | 期间成果 10，overlap 94 月 |
| 3 | a=person_c8669294(张沕琳) b=person_c9915341(向德辉) 2020-01~2024-12 | 期间成果 3，overlap 82 月（濠江測試數碼 033） |
| 4 | a=person_9A62597r(费政聪) b=person_99a94795(彭海琳) 2020-01~2024-12 | total=1，共同机构=深圳市意天科技有限公司，overlap 82 月，期间成果 3，有效期 2020-01~2026-10 |
| 5 | a=person_8196m452(李坚强) b=person_20N32Z57(沈忱) 2015-01~2026-08 | total=1，共同机构=清华大学计算机科学与技术系，overlap 94 月，期间成果 0 |
| 附 | 林毅(person_827Hu6J4)×陈超越(person_83501Q44) | overlap 118 月，成果 0 |

## M5 校友关系 `kg-construction/expert-alumni-relations/query`

⚠️ 可用对集中在 9F9A00xx **演示种子人员**（真人教育背景仅 ~24/19 万）；kgtest_20260721 系列教育属性 mojibake（ä¸­å›½…）不可查。

| 组 | 输入 | 实跑 |
|---|---|---|
| 1 | 9F9A0084(顾清妍)×9F9A0096(常舒宁) 上海交通大学 博士 | 同校+同学历+同期 ✓ |
| 2 | 9F9A0092(武清歌)×9F9A0084(顾清妍) 上海交通大学 | 同校（异学历样本）✓ |
| 3 | 9F9A0098(裴诗雅)×9F9A0066(熊若兰) 北京大学 学士 | 同校+同学历+同期 ✓ |
| 4 | person_9F9A0001(陈明远)×person_9F9A0004(张若琳) 清华大学 博士 | 同校+同学历+同期 ✓ |
| 5 | person_9F9A0058(姜悦宁)×person_9F9A0061(石俊熙) 华中科技大学 博士 | 同校+同学历+同期 ✓ |

## M6 论文合作 `kg-construction/expert-paper-cooperation-relations/structured-result`

⚠️ citation 恒 0（被引未接入）；authorUnits 来自人员属性而非论文 affiliation。**组 4/5/6 论文年份字段为空，须 `startTime:""` `endTime:""` 无窗**（带窗全滤 0）。

| 组 | 输入 | 实跑 |
|---|---|---|
| 1 | A=person_1D693hk4 B=person_2y1H981f(F. Richard Yu) | ~~116 篇~~ **10-28 实跑 0**（重灌桩点，论文边没了）→ 已由组 4-6 替补 |
| 2 | A=person_0209a7v6 B=person_1S5195f4 2015-01~2026-08 | 18 篇，2015-2020，impact 99.5 |
| 3 | A=person_1D693hk4 B=person_8196m452 2015-01~2026-08 | 13 篇，2020-2023，impact 84.5 |
| 4 | A=person_060S790j(孙哲浩) B=person_20N32Z57(沈忱) **无窗空串** | 11 篇，impact 71.5，freq 11（跨机构：北大×清华） |
| 5 | A=person_8196m452(李坚强) B=person_21o9K09L(Qiuzhen Lin) 2015-01~2026-08 | 4 篇，2020-2023，impact 26 |
| 6 | A=person_8196m452(李坚强) B=person_11J730iM(潘毅) **无窗空串** | 5 篇，impact 32.5 |
| 附 | A=person_0209a7v6 B=person_4W4791544(Jingkun Zhao) | ~~90 篇~~ **10-28 实跑 0**（同组 1 原因） |

## M7 重点企业关系 `kg-service/key-enterprise-relation`

| 组 | 输入 | 实跑 |
|---|---|---|
| 1 | person_aa21276d13af5bb7f5d03ae1ea18a3ce(舒达坤) 优鹰智能科技(深圳)有限公司 董事长 无人机系统 | L1 高管任职，tech_field 命中，风险=暂无 |
| 2 | person_224231f397fd5ee63a301ad7e82271d1 浙江大华技术股份有限公司 副总经理 云台摄像机、无人机系统 | L1，已上市企业 |
| 3 | person_116c41f92ecebd7f3f8344b11a616bef 优鹰 董事 无人机系统 | L1 |
| 4 | person_3e41f9c8793e37e48a5b623c8ed6af4a 瑞芯微电子股份有限公司 财务负责人 主控芯片、集成电路设计 | 命中（role_level None） |
| 5 | person_3f3362d359d8ad83730c2f1e683f9147 深圳市翔农创新科技有限公司 董事 无人机系统、植保无人机 | 命中 |
| 附 | 赛奥航空 person_617880bd9c99feaffa02c47da50a8f53 执行董事 / 砺剑天眼 person_0294f471d3bfa5b843bd5ba98c7482d4 监事 | 均命中 |

⚠️ 合作时间恒空（任职日期属性全空）；风险提示恒"暂无"（司法事件未挂边）；财务负责人/监事 role_level 为 None。

## M8 节点头部事件 `kg-service/industry-node-top-events`

⚠️ time_range_end **不能晚于当前月**（422 校验错）。

| 组 | 输入 | 实跑 |
|---|---|---|
| 1 | IC0007007 集成电路设计 annual_finance top10 | events=10，豪威 436 亿年报 rank1，士兰微 267 亿；risk_level 中 |
| 2 | IC9901077 云台摄像机 recruit top5 | events=5 全部浙江大华招聘 |
| 3 | IC9901090 民用无人机 financing top5 | events=3，翔农创新 A 轮 1000 万 rank1 |
| 4 | IC0007005 集成电路 annual_finance top10 | events=10，北方华创 898 亿 rank1 |
| 5 | IC9901106 低空经济 financing top5 | events=3，翔农创新 A 轮 1000 万 rank1 |
| 6 | IC0007012 annual_finance top5 | events=5，士兰微 267 亿 rank1 |

（IC0007022 recruit 实跑 0 条，勿用。）

## M9 产业链全景 `kg-construction/industry-chain-panorama/query`

| 组 | 输入 | 实跑 |
|---|---|---|
| 1 | 集成电路 anchor=node_IC0007004 depth2 topK5 | 核心技术4+领军企业5+领军专家3+产业动态2 |
| 2 | 低空经济 anchor=node_IC9901036 depth2 topK5 | 基建设施1+企业5+专家3（李钊 H28）+事件0 |
| 3 | 集成电路 anchor=node_IC0007007 depth3 topK10 | 4+10+2+3（含股权/战略融资事件） |
| 4 | 集成电路 anchor=node_IC0007005 depth2 topK5 | 4+5+3+2 |
| 5 | 低空经济 anchor=node_IC9901090 depth2 topK5 | 1+5+3+0 |

❌ 人工智能链 0 节点不可用。

## 结构性缺口汇总（vs 远端 dev 空间）

1. M1 时间窗不可用（边无 relation_time）
2. M3 专利单人、获奖全空
3. M5 真人教育背景 24/19 万，依赖演示种子
4. M6 被引恒 0
5. M7 合作时间空、风险提示恒暂无（司法事件悬挂无边）
6. 人工智能产业链空
7. AFFILIATED_WITH 仅 81 条、多人机构仅 3 个（清华CS系 53 人/意天科技 13 人/濠江演示 15 人）；**同机构+共同论文对全图仅 3 对**
8. kgtest 系列教育/姓名 mojibake
9. **重灌后共同论文年份字段为空** → M3/M6 带窗归零（M3 须省略时间字段、M6 须空串无窗）
10. M7/M8 查询后端有"写回实体置信度失败 POST /api/v1/query/write 400 wrong value type"旁支报错（非致命，结果正常，属服务缺陷）

---
验证脚本与原始 JSON： `~/.claude/jobs/2d67a5da/tmp/`（phaseB_dp_gkx.py、dp_gkx_phaseB.json、dp_gkx_phaseB_fix.json）；扩组批次 `~/.claude/jobs/3f2ae053/tmp/`（nine5_run.py/nine5_b2.py/nine5_b3.py/nine5_b4.py/nine5_b5.py 及对应 *_out/b*.json）。
