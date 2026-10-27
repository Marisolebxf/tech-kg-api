-- gkx_kg_v2 学者机构合并审计件（kg_scholar_organization 45 行 → v_organization 三档并入）
-- 依据 20261028 实测；配套报告 ~/deploy/gkx-kg-v2-build-report-1028.md
-- 可直接对源库 gkx_kg 只读执行复核

-- ══════════ 分档总览 ══════════
-- ①同键 3 行：企业行已在 kg_organization（濠江測試數碼有限公司033 / 深圳市意天科技有限公司 /
--   清华大学计算机科学与技术系），不导；其 81 条 affiliated_with 边天然落企业键。
-- ②同名不同键 17 行：不插行（插行=同机构双顶点），252 条边 dst 改写至同名企业键（明细见下）。
-- ③纯学术缺失 25 行：INSERT 进 v_organization，props 12 键逐字段展开（7 键落既有列 +
--   confidence 落新列 + id/name 冗余 + create/update_time 由图审计列承载），796 条边落新键。
--   合计 81 + 252 + 796 = 1,129 条 affiliated_with 全部落 Organization 顶点。

-- ══════════ ②档 17 对键映射明细（每名唯一匹配，无 fanout；目标键零 MOCK/引号脏）══════════
-- 机器可读版见下方 SELECT；人读版：
--   上海优宁维生物科技股份有限公司     org_c9f0aeedec969a7a → org_059513c5797a1d7a3dfc8f8869c121d9  15 条
--   深圳前海骁客影像科技设计有限公司   org_416f915d6dd55986 → org_040dd8acf11fa9dd34b6a4d85d5a1a81  15 条
--   法狮龙家居建材股份有限公司         org_d28659e2040f5597 → org_0344e298274b97c8d5ae73c4ca56d7eb  15 条
--   曼卡龙珠宝股份有限公司             org_ce99386b26af7572 → org_04f92753c7f5da3b263b4fcc0f63adf9  15 条
--   宁夏凯添燃气发展股份有限公司       org_8db6a0babaf97e2c → org_045d4a9b4621c5ef43acc5843955a157  15 条
--   四川安宁铁钛股份有限公司           org_99d7d661612b4626 → org_0450afbd6e538fc350907b69806a91a5  15 条
--   金徽矿业股份有限公司               org_50c0d243346a9821 → org_04305390561d54bd193d03223b74c9ab  15 条
--   广东冠豪高新技术股份有限公司       org_4b0035278409f065 → org_015e387d77361b95b2f6953a92059510  15 条
--   深圳市英威腾电气股份有限公司       org_2872f986f442dc89 → org_04b75452bd230e38bd160bb12c13ce9e  15 条
--   徐工集团工程机械股份有限公司       org_8e29e54ff2065732 → org_047583dfefe252480e530d15c0d436df  15 条
--   东方财富信息股份有限公司           org_c80fc5d270af0bbc → org_04396b49d8e61600c5df4122d01255d4  15 条
--   上海雅创电子集团股份有限公司       org_5152a01ff74054f8 → org_03226042bc98f15da8af47dfef8c3612  15 条
--   深圳市劲拓自动化设备股份有限公司   org_03bb3039720c5388 → org_02c54b80822a08444c66d4f8be9d5304  15 条
--   金能科技股份有限公司               org_0a0c3cfc66a9173c → org_028b0a4ebfb6ecaf48288dbd14272b33  15 条
--   新智认知数字科技股份有限公司       org_988fc53d4950af9c → org_000213e718b09bd45e71789553cc53d7  15 条
--   北京航空材料研究院股份有限公司     org_625476ac3c7a83fc → org_00a94a6adc3c65b318b7aeb0ea240ef9  14 条
--   江苏徐矿能源股份有限公司           org_7cf77bdebc5e134e → org_057bd3d003c92ce097d82d9beeba3e2d  13 条
--   合计 252 条 ✓

-- ②档映射（对源库只读复核）：
SELECT s.name_zh AS 机构名,
       CONCAT('org_', s.org_id) AS 旧学者键vid,
       CONCAT('org_', o.org_id) AS 企业键vid,
       (SELECT COUNT(*) FROM gkx_kg.ev_affiliated_with e
         WHERE e.dst_id = CONCAT('org_', s.org_id)) AS 待改写边数
FROM gkx_kg.kg_scholar_organization s
JOIN gkx_kg.kg_organization o
  ON o.name_cn COLLATE utf8mb4_general_ci = s.name_zh COLLATE utf8mb4_general_ci
WHERE NOT EXISTS (SELECT 1 FROM gkx_kg.kg_organization k WHERE k.org_id = s.org_id)
ORDER BY s.name_zh;

-- ══════════ ③档 25 行学者合并（props 展开口径，即 04 脚本中的 INSERT）══════════
-- 学者行 confidence=0.6（物化自 dwd_scholar_work_experience），org_kind=scholar_affiliation
SELECT s.org_id, s.name_zh, s.name_en,
       JSON_UNQUOTE(JSON_EXTRACT(s.props, '$.org_kind'))   AS org_kind,
       JSON_UNQUOTE(JSON_EXTRACT(s.props, '$.source_table')) AS source_table,
       JSON_UNQUOTE(JSON_EXTRACT(s.props, '$.source_record_id')) AS source_record_id,
       JSON_UNQUOTE(JSON_EXTRACT(s.props, '$.ingest_batch')) AS ingest_batch,
       JSON_UNQUOTE(JSON_EXTRACT(s.props, '$.ingest_time')) AS ingest_time,
       CAST(JSON_EXTRACT(s.props, '$.confidence') AS DOUBLE) AS confidence
FROM gkx_kg.kg_scholar_organization s
WHERE NOT EXISTS (SELECT 1 FROM gkx_kg.kg_organization k WHERE k.org_id = s.org_id)
  AND NOT EXISTS (SELECT 1 FROM gkx_kg.kg_organization o WHERE o.name_cn = s.name_zh);

-- ══════════ 建成后自检（gkx_kg_v2 内执行，期望值如注）══════════
SELECT COUNT(*) FROM v_organization;                                   -- 19,895（19,870 企业 + 25 学者）
SELECT COUNT(*) FROM v_organization WHERE confidence IS NOT NULL;      -- 25（全 =0.6）
SELECT COUNT(*) FROM ev_affiliated_with;                               -- 1,129
SELECT COUNT(*) FROM ev_affiliated_with e                              -- 0（旧学者键残留应为零）
  LEFT JOIN v_organization o
    ON o.org_id = SUBSTRING(e.dst_id, 5) COLLATE utf8mb4_general_ci
 WHERE o.org_id IS NULL;                                               -- dst 全部可解析
