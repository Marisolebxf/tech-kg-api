USE `dev_graph_restore_20261026`;

-- 实际导出的实体节点与缺属性端点分开计数。
SELECT `is_missing`, COUNT(*) AS `nodes`
FROM `kg_node_index` GROUP BY `is_missing`;

SELECT `inferred_schema`, COUNT(*) AS `nodes_to_complete`
FROM `kg_missing_node` GROUP BY `inferred_schema`;

-- 一行一位人物，id 是本次重新分配的表主键。
SELECT `id`, `name_zh`, `name_en`, `scholar_org`, `source_table`
FROM `kg_person` LIMIT 10;

-- 一行一条合著边，两端指向新的节点关联键。
SELECT `id`, `from_id`, `to_id`, `co_paper_count`, `confidence`, `source_table`
FROM `kg_edge_coauthor_with` LIMIT 10;

-- 只展示两端均有实际人物属性的合著边。
SELECT e.`id`, e.`from_id`, a.`name_zh` AS `from_name`,
       e.`to_id`, b.`name_zh` AS `to_name`, e.`co_paper_count`
FROM `kg_edge_coauthor_with` e
JOIN `kg_person` a ON a.`id` = e.`from_id`
JOIN `kg_person` b ON b.`id` = e.`to_id`
WHERE a.`name_zh` IS NOT NULL AND a.`name_zh` <> ''
  AND b.`name_zh` IS NOT NULL AND b.`name_zh` <> ''
LIMIT 10;

-- 给新系统使用的单个 Person 输入视图；占位行仅提供关联键。
SELECT `_is_placeholder`, COUNT(*) AS `rows`
FROM `v_input_person` GROUP BY `_is_placeholder`;

SELECT e.`id`, e.`from_id`, a.`name_zh` AS `from_name`,
       a.`_is_placeholder` AS `from_is_placeholder`,
       e.`to_id`, b.`name_zh` AS `to_name`,
       b.`_is_placeholder` AS `to_is_placeholder`, e.`co_paper_count`
FROM `kg_edge_coauthor_with` e
JOIN `v_input_person` a ON a.`id` = e.`from_id`
JOIN `v_input_person` b ON b.`id` = e.`to_id`
LIMIT 10;
