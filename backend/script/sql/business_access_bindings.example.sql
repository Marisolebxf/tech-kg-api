-- kgetl business RBAC 初始化模板。所有写语句故意注释，复制到工单并替换占位符后逐项执行。
-- 不预置真实用户、业务、空间、资源ID；先用 migrate_business_access.py --apply 迁移结构。
-- 连接目标是业务库 MYSQL_DATABASE，不是凭猜测选择的控制库。

-- 1. 业务ID是本系统租户标识，不复用OAuth应用client_id或外部API密钥client_id。
-- INSERT INTO kg_business_client (client_id, name, enabled)
-- VALUES ('<replace_business_client_id>', '<replace_business_name>', 1);

-- 2. 账号ID取统一认证 userInfo.id，不能用登录名、昵称、邮箱替代。
-- 一个账号当前只能归属一个业务，user/developer为业务角色；admin另见第3项。
-- INSERT INTO kg_business_member (user_id, client_id, role)
-- VALUES ('<replace_auth_user_id>', '<replace_business_client_id>', 'developer');
-- UPDATE kg_business_member SET role = 'user'
-- WHERE user_id = '<replace_exact_auth_user_id>' AND client_id = '<replace_expected_business_id>';

-- 3. 已登录平台的账号可授予本地管理员；保留原有管理员，不批量撤权。
-- 门户管理员需要运行后台任务时，也须明确授予本地platform_admin，门户快照不是授权。
-- INSERT INTO kg_platform_user_role (id, user_id, role_code, granted_by)
-- SELECT UUID(), u.user_id, 'platform_admin', '<replace_operator_user_id>'
-- FROM kg_platform_user AS u
-- WHERE u.user_id = '<replace_existing_auth_user_id>'
--   AND NOT EXISTS (
--     SELECT 1 FROM kg_platform_user_role AS r
--     WHERE r.user_id = u.user_id AND r.role_code = 'platform_admin'
--   );

-- 4. 图空间必须已经在图数据库中存在。这里只登记归属，不创建Nebula/Milvus空间。
-- INSERT INTO kg_business_graph_space (space_name, client_id, is_shared_production, shared_key)
-- VALUES ('<replace_existing_private_space>', '<replace_business_client_id>', 0, NULL);
-- 共享生产空间必须等于所有API/worker进程的TRS_GRAPH_SPACE；shared_key唯一槽位固定production。
-- INSERT INTO kg_business_graph_space (space_name, client_id, is_shared_production, shared_key)
-- VALUES ('<replace_TRS_GRAPH_SPACE>', NULL, 1, 'production');
-- 禁止把所有旧kg_user_graph_space自动转换为业务归属：旧绑定允许多人/多业务，需逐空间核实。

-- 5. 历史配置按明确ID归属业务；不根据旧owner的当前业务自动批量迁移。
-- 以下UPDATE有旧owner条件，避免覆盖并发修改。每种资源先核对业务、ID和当前owner。
-- UPDATE platform_llm_config SET owner = 'business:<replace_client_id>'
-- WHERE id = '<replace_llm_config_id>' AND owner = '<replace_expected_old_owner>';
-- UPDATE platform_embedding_config SET owner = 'business:<replace_client_id>'
-- WHERE id = '<replace_embedding_config_id>' AND owner = '<replace_expected_old_owner>';
-- UPDATE platform_milvus_config SET owner = 'business:<replace_client_id>'
-- WHERE id = '<replace_milvus_config_id>' AND owner = '<replace_expected_old_owner>';
-- UPDATE platform_mysql_datasource SET owner = 'business:<replace_client_id>'
-- WHERE id = '<replace_mysql_datasource_id>' AND owner = '<replace_expected_old_owner>';
-- 默认配置应在同一业务内明确选择；不把已有生产配置或密钥复制到其他业务。

-- 6. 无法从历史快照确定空间的审核记录：核对原始执行/来源后按case ID手工补齐。
-- 仅补NULL，不用当前默认空间覆盖未知归属，不改已有正确记录。
-- UPDATE manual_review_case SET graph_space = '<replace_verified_space>'
-- WHERE id = '<replace_exact_review_case_id>' AND graph_space IS NULL;

-- 以下为只读核对，不包含配置密钥/令牌/快照内容。
SELECT m.user_id, m.client_id, m.role
FROM kg_business_member AS m LEFT JOIN kg_business_client AS b ON b.client_id = m.client_id
WHERE b.client_id IS NULL OR m.role NOT IN ('user', 'developer');

SELECT g.space_name, g.client_id, g.is_shared_production, g.shared_key
FROM kg_business_graph_space AS g LEFT JOIN kg_business_client AS b ON b.client_id = g.client_id
WHERE (g.is_shared_production = 0 AND (g.client_id IS NULL OR b.client_id IS NULL))
   OR (g.is_shared_production = 1 AND (g.shared_key IS NULL OR g.shared_key <> 'production'))
   OR (g.is_shared_production = 0 AND g.shared_key IS NOT NULL);

SELECT space_name, shared_key FROM kg_business_graph_space WHERE is_shared_production = 1;
SELECT COUNT(*) AS unresolved_review_cases FROM manual_review_case
WHERE graph_space IS NULL OR graph_space = '';
SELECT DISTINCT c.graph_space AS unregistered_review_space
FROM manual_review_case AS c LEFT JOIN kg_business_graph_space AS g ON g.space_name = c.graph_space
WHERE c.graph_space IS NOT NULL AND g.space_name IS NULL;

SELECT id, owner FROM platform_llm_config WHERE owner NOT LIKE 'business:%';
SELECT id, owner FROM platform_embedding_config WHERE owner NOT LIKE 'business:%';
SELECT id, owner FROM platform_milvus_config WHERE owner NOT LIKE 'business:%';
SELECT id, owner FROM platform_mysql_datasource WHERE owner NOT LIKE 'business:%';

-- 对业务范围默认配置的重复项逐项处理，禁止不分业务重置所有is_default。
SELECT owner, COUNT(*) AS default_count FROM platform_llm_config
WHERE is_default = 1 GROUP BY owner HAVING COUNT(*) > 1;
SELECT owner, COUNT(*) AS default_count FROM platform_embedding_config
WHERE is_default = 1 GROUP BY owner HAVING COUNT(*) > 1;

SELECT r.id, r.client_id, r.space_name, r.status, r.active_space_name
FROM kg_business_space_request AS r
WHERE (r.status IN ('pending', 'creating', 'failed') AND r.active_space_name IS NULL)
   OR (r.status IN ('ready', 'rejected') AND r.active_space_name IS NOT NULL);
