# gkx_kg_v2 图空间·九大业务可命中测试数据清单（2026-10-27 实跑验证，46 组）

- 空间： 本机 trsgraph `gkx_kg_v2`（14 TAG 1,025,180 点 / 25 EDGE 1,159,390 边；来源 39 张表 = 本目录两卷 SQL）
- 验证方式： dev2 容器内 ASGI 直调（`X-Business-Graph-Space: gkx_kg_v2`），全部查询端点，只读；输入可直接抄用，端点前缀均 `/api/v1`
- 重放器与原始 JSON： `~/.claude/jobs/3f2ae053/tmp/nine_v2_replay.py` / `nine_v2_out.json`（51 调用）
- 总判定： **42/46 与 dp_gkx 基线（docs/nine-modules-testdata-1027.md，分支 docs/nine-modules-testdata-dp-gkx-1027）逐字一致；4 组差异全部有据**——M2-3 1/2/2→6/7/7（学者机构并入 Organization 的合并增益）、M2-5 116→110、M4-3/M4-4 成果 3→0（dp_gkx 图里的 889900 演示论文被 v2 按口径排除，详见文末）

## M1 直接关系 `kg-construction/expert-direct-relations/query`

⚠️ **不要带 startTime/endTime**： COAUTHOR_WITH 边无 relation_time 属性，一带时间窗即全被滤空（reason=empty_result）。

| 组 | 输入 | 实跑结果 |
|---|---|---|
| 1 | A=person_0209a7v6(赵刚) B=person_1S5195f4(朱保君) institution=清华大学计算机科学与技术系 | total=1，同机构+共论文，coPaperCount=18，strength=89，代表成果 3 条 |
| 2 | A=person_1D693hk4(梁中明) B=person_8196m452(李坚强) institution=清华大学计算机科学与技术系 | total=1，同机构+共论文，26，93 |
| 3 | A=person_060S790j(孙哲浩) B=person_20N32Z57(沈忱) | total=1，共论文，12，86 |
| 4 | A=person_uF227379(王翊) B=person_154p2738(王毅) | total=1，共论文，918（COAUTHOR_WITH 权重口径），99 |
| 5 | A=person_ij9647339(王祎) B=person_154p2738(王毅) | total=1，共论文，918，99 |

## M2 间接关系 `kg-construction/expert-indirect-relations/demo/structured-result`

| 组 | core_node_id | relation_types | 实跑（直接/间接/路径，avgStrength） |
|---|---|---|---|
| 1 | person_0209a7v6 赵刚 | [学术关联] depth2 min0.3 | 26 / 126 / 147，0.70 |
| 2 | person_1D693hk4 梁中明 | [学术关联] | 31 / 285 / 315，0.69 |
| 3 | person_8196m452 李坚强 | [机构关联] | **6 / 7 / 7**，0.58（基线 1/2/2 → 差异=合并增益，见文末①） |
| 4 | person_2y1H981f F.R.Yu | [学术关联] depth2 min0.3 | 4 / 347 / 395，0.74 |
| 5 | person_uF227379 王翊 | [学术关联] depth2 min0.3 | 26 / 107 / **110**，0.65（基线 116 → 差异=演示论文排除，见文末②） |

## M3 合作成果 `kg-construction/expert-cooperation-achievements/query`

⚠️ 组 2/4/5 的共同论**文年份字段为空**，时间字段（timeRangeStart/End）**必须整体省略**——带任意窗口全滤 0（探针 M3-5w 实证），传空串 422。年份在的组（1/3）可带窗。

| 组 | 输入 | 实跑 |
|---|---|---|
| 1 | source=person_0209a7v6 target=person_1S5195f4 types=[论文] 2015-01~2026-08 | papers=18（首条《…600-T 磁场》） |
| 2 | source=person_1D693hk4 target=person_8196m452 types=[全部]（无时间字段） | papers=3 |
| 3 | source=person_5k153q31 target=person_710a42c569116e972ee82a36f227276f types=[全部] 2000-01 起 | **projects=1**（BESIII 国家级项目） |
| 4 | source=person_8196m452(李坚强) target=person_21o9K09L(Qiuzhen Lin) types=[论文] 2015-01~2026-08 | papers=3（清华×深圳大学） |
| 5 | source=person_8196m452(李坚强) target=person_84ed6ph4(明仲) types=[全部]（无时间字段） | **items=17**（首条《UAV/UGV 协同系统混合路径规划》） |

## M4 同事关系 `kg-service/expert-colleague-relation`

匹配逻辑 = 两人 AFFILIATED_WITH 任职边指向同一机构顶点 + 任职期交集。v2 的 AFFILIATED_WITH 已 1,129 条全部落 Organization（含并入的 25 学者机构）。

| 组 | 输入 | 实跑 |
|---|---|---|
| 1 | a=person_0209a7v6 b=person_1S5195f4 2015-01~2026-08 | total=1，清华CS系/智能计算研究室，overlap 106 月，期间成果 7 |
| 2 | a=person_1D693hk4 b=person_8196m452 2015-01~2026-08 | total=1，清华CS系，overlap 94 月，期间成果 10 |
| 3 | a=person_c8669294(张沕琳) b=person_c9915341(向德辉) 2020-01~2024-12 | total=1，濠江測試數碼有限公司033/协同创新研究室，overlap 82 月，期间成果 **0**（基线 3 → 差异=演示论文排除，见文末②） |
| 4 | a=person_9A62597r(费政聪) b=person_99a94795(彭海琳) 2020-01~2024-12 | total=1，深圳市意天科技有限公司，overlap 82 月，期间成果 **0**（基线 3，同上） |
| 5 | a=person_8196m452(李坚强) b=person_20N32Z57(沈忱) 2015-01~2026-08 | total=1，清华CS系，overlap 94 月，期间成果 0 |

## M5 校友关系 `kg-construction/expert-alumni-relations/query`

可用对集中在 9F9A00xx **演示种子人员**（真人教育背景稀疏；v2 的 v_person 未排除 9F9A，如实保留）。

| 组 | 输入 | 实跑 |
|---|---|---|
| 1 | person_9F9A0084(顾清妍)×person_9F9A0096(常舒宁) 上海交通大学 博士 | total=1，同校+同学历+同期 ✓（conf 0.92） |
| 2 | person_9F9A0092(武清歌)×person_9F9A0084(顾清妍) 上海交通大学 | total=1，同校 ✓（conf 0.72） |
| 3 | person_9F9A0098(裴诗雅)×person_9F9A0066(熊若兰) 北京大学 学士 | total=1 ✓（conf 0.92） |
| 4 | person_9F9A0001(陈明远)×person_9F9A0004(张若琳) 清华大学 博士 | total=1 ✓（conf 0.86） |
| 5 | person_9F9A0058(姜悦宁)×person_9F9A0061(石俊熙) 华中科技大学 博士 | total=1 ✓（conf 0.80） |

## M6 论文合作 `kg-construction/expert-paper-cooperation-relations/structured-result`

⚠️ citation 恒 0（被引未接入，结构性缺口）。**组 4/6 论文年份字段为空，须 `startTime:""` `endTime:""` 无窗**（带窗全滤 0，探针 M6-4w=0；组 6 中 1 篇有 2022 年份，加窗后剩 1，探针 M6-6w=1）。

| 组 | 输入 | 实跑 |
|---|---|---|
| 2 | A=person_0209a7v6 B=person_1S5195f4 2015-01~2026-08 | 18 篇，2015-2020，impact 99.5 |
| 3 | A=person_1D693hk4 B=person_8196m452 2015-01~2026-08 | 13 篇，2020-2023，impact 84.5 |
| 4 | A=person_060S790j(孙哲浩) B=person_20N32Z57(沈忱) **无窗空串** | 11 篇，impact 71.5，freq 11（北大×清华） |
| 5 | A=person_8196m452(李坚强) B=person_21o9K09L(Qiuzhen Lin) 2015-01~2026-08 | 4 篇，2020-2023，impact 26 |
| 6 | A=person_8196m452(李坚强) B=person_11J730iM(潘毅) **无窗空串** | 5 篇，2022-2022，impact 32.5 |

（基线组 1 梁×F.R.Yu 与附组 赵×Jingkun Zhao 为 dp_gkx 死亡对，v2 探针 M6-P1/P2 均 0，两空间一致仍死。）

## M7 重点企业关系 `kg-service/key-enterprise-relation`

| 组 | 输入 | 实跑 |
|---|---|---|
| 1 | person_aa21276d13af5bb7f5d03ae1ea18a3ce(舒达坤) 优鹰智能科技(深圳)有限公司 董事长 无人机系统 | L1 高管任职，tech_field 命中，风险=暂无 |
| 2 | person_224231f397fd5ee63a301ad7e82271d1(刘明) 浙江大华技术股份有限公司 副总经理 云台摄像机、无人机系统 | L1，已上市企业 |
| 3 | person_116c41f92ecebd7f3f8344b11a616bef(郭晓磊) 优鹰 董事 无人机系统 | L1 |
| 4 | person_3e41f9c8793e37e48a5b623c8ed6af4a(王海闽) 瑞芯微电子股份有限公司 财务负责人 主控芯片、集成电路设计 | 命中，role_level None（任职期空） |
| 5 | person_3f3362d359d8ad83730c2f1e683f9147(钟启龙) 深圳市翔农创新科技有限公司 董事 无人机系统、植保无人机 | L1 |

⚠️ 合作时间恒空（任职日期属性全空）；风险提示恒"暂无"（司法事件未挂边）；财务负责人/监事 role_level 为 None。查询有"写回实体置信度 400"旁支报错（服务层既有缺陷，非本空间问题，结果正常）。

## M8 节点头部事件 `kg-service/industry-node-top-events`

⚠️ time_range_end **不能晚于当前月**（422 校验错）。

| 组 | 输入 | 实跑 |
|---|---|---|
| 1 | IC0007007 集成电路设计 annual_finance top10 | events=10（org 10/专家 9），豪威 436 亿年报 rank1，士兰微 267 亿；risk_level 中 |
| 2 | IC9901077 云台摄像机 recruit top5 | events=5（org 1/专家 16）全部浙江大华招聘（rank1 海外市场产品专家） |
| 3 | IC9901090 民用无人机 financing top5 | events=3（org 1/专家 4），翔农创新 A 轮 1000 万 rank1 |
| 4 | IC0007005 半导体设备 annual_finance top10 | events=10，北方华创 898 亿 rank1 |
| 5 | IC9901106 遥感测绘无人机 financing top5 | events=3，翔农创新 A 轮 1000 万 rank1 |
| 6 | IC0007012 集成电路制造服务 annual_finance top5 | events=5（org 5），士兰微 267 亿 rank1 |

## M9 产业链全景 `kg-construction/industry-chain-panorama/query`

| 组 | 输入 | 实跑（核心技术/领军企业/领军专家/产业动态） |
|---|---|---|
| 1 | 集成电路 anchor=node_IC0007004 depth2 topK5 | 4/5/3/2（图 356 点 385 边） |
| 2 | 低空经济 anchor=node_IC9901036 depth2 topK5 | 1/5/3/0（图 102 点 100 边） |
| 3 | 集成电路 anchor=node_IC0007007 depth3 topK10 | 4/10/2/3（图 323 点 332 边） |
| 4 | 集成电路 anchor=node_IC0007005 depth2 topK5 | 4/5/3/2 |
| 5 | 低空经济 anchor=node_IC9901090 depth2 topK5 | 1/5/3/0 |

（人工智能链 0 节点不可用，与基线一致。）

## 4 组差异归因（全部有 SQL 证据）

1. **M2-3（1/2/2→6/7/7，变多）= 合并设计的预期效果**：dp_gkx 里李坚强的 AFFILIATED_WITH 指向学者机构独立顶点；v2 合并后落在 Organization 顶点，企业任职边+学者任职边的同机构圈子打通 → 直接节点 1→6。
2. **M2-5（116→110）/ M4-3 / M4-4（成果 3→0）= 889900 演示论文排除**：两对专家的共同论文只有 paper_889900085~090（濠江对）/085~087（意天对）；王翊名下 3 篇 889900 论文 ×路径扇出 = 6 条学术路径。dp_gkx 把演示论文写进了图，v2 沿用排除口径（Paper id NOT LIKE '889900%'，17 篇）。

## 探针结论

| 探针 | 结果 | 说明 |
|---|---|---|
| M6-P1 梁×F.R.Yu / M6-P2 赵刚×Jingkun Zhao | 0 / 0 | 死亡对仍死（源表即无共同论文，两空间一致） |
| M3-5w（M3-5 加窗 2015-2026） | 0 | 论文年份空带窗全滤 0，坑在 v2 延续 |
| M6-4w（M6-4 加窗） | 0 | 同上 |
| M6-6w（M6-6 加窗） | 1 | 5 篇中 1 篇 publication_year=2022，带窗语义正确 |

## v2 结构性缺口延续情况（对照基线文档 10 条）

- **延续**：#1 M1 时间窗（COAUTHOR_WITH 无 relation_time）、#3 真人教育背景稀疏（M5 依赖演示种子）、#4 M6 被引恒 0、#5 M7 合作时间空/风险恒暂无、#6 人工智能产业链空、#8 kgtest mojibake、#9 论文年份大多空（M3-5w/M6-4w 证实；M6-6w 证明个别有年份）、#10 M7/M8 写回置信度 400 旁支报错
- **改善**：#7 AFFILIATED_WITH 81 条 → v2 **1,129 条全部落 Organization**（81 同键 + 252 键对齐改写 + 796 新学者键），同机构圈子明显变大（M2-3 即证据）；排除演示论文后全图"同机构+共同论文"真人对仅赵刚×朱保君 1 对（数仓侧论文数据真实状态）
- #2（专利单人/获奖全空）延续，非本空间问题
