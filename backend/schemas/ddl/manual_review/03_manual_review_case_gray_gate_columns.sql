-- gray-gate-v2 第一阶段迁移之二：manual_review_case 来源账本计数列（选项 A 显式列）。
-- source_count=不同来源总数；source_truncated_count=未存 evidence 的截断来源数。
-- 逻辑计数由追加事务维护（SELECT...FOR UPDATE 锁案行 → INSERT → UPDATE 计数）。
-- 注意：本文件随分支提交，实际执行 DDL 属部署审批范围（第一阶段明确不执行）。

ALTER TABLE manual_review_case ADD COLUMN source_count INTEGER NOT NULL DEFAULT 0, ADD COLUMN source_truncated_count INTEGER NOT NULL DEFAULT 0;
