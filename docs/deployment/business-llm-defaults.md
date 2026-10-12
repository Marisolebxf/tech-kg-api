# 业务默认语言模型

部署前先暂停配置写入，在后端目录运行 `python script/migrate_business_llm_defaults.py`，检查现有公共默认数量和归属，以及已有公共/业务默认是否缺失、停用、缺少密钥、跨业务或所属业务已失效。业务专属模型被标记为全局默认、多个全局默认时退出且不修改数据；需明确修复现有默认后重跑，不能自动挑选替代模型。

检查通过后执行 `python script/migrate_business_llm_defaults.py --apply`，幂等创建 `platform_business_llm_default` 空表，先部署并确认新工作进程已注册默认模型解析 activity，再部署新后端 API 和前端，避免新任务调度到不支持新 activity 的旧 worker。已有业务默认记录不会被覆盖。新装库的 `script/init_db.py` 同样包含此表 DDL。

平台默认仍使用 `platform_llm_config.is_default`，只允许公共模型。业务选择只更新新表，同业务共享；无记录跟随平台默认。选中的配置失效时报告错误，不静默改用其他模型。停用或删除前校验所有默认引用。

回滚应用前需注意旧版本不识别业务默认：应保留新表和数据，不能宣称旧版继续执行业务选择。迁移不修改旧配置归属、密钥或旧默认字段。
