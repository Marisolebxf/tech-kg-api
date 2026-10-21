-- gray-gate-v2 第一阶段迁移之三：T_LINK 裁决应用标记表（priorVerdict.applyStatus 耐久落点）。
-- 四态 NOT_REQUIRED / APPLIED / FAILED / UNKNOWN（UNKNOWN=两段提交意图标记初值与崩溃窗口
-- 收敛态；存量旧案缺整行同样按 UNKNOWN 失败关闭，不补录——历史补录另行审批）。
-- 两段提交：Tx1 决议+意图标记（reject 直接 NOT_REQUIRED）→ 图写 → Tx2 改 APPLIED/FAILED。
-- 注意：本文件随分支提交，实际执行 DDL 属部署审批范围（第一阶段明确不执行）。

CREATE TABLE manual_review_verdict_application (
	id INTEGER NOT NULL AUTO_INCREMENT,
	case_id VARCHAR(64) NOT NULL,
	decision_id INTEGER,
	verdict VARCHAR(32) NOT NULL,
	apply_status VARCHAR(32) NOT NULL,
	canonical_vid VARCHAR(256),
	reserved_vid VARCHAR(256),
	error_code VARCHAR(64),
	applied_at DATETIME,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uk_review_verdict_application_case UNIQUE (case_id)
);
