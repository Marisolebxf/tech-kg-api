# 国内外机构 MySQL → 图数据库执行入口

甲方服务器已经完整部署 `tech-kg-api`，因此本目录不再复制项目源码。这里的入口直接复用上级 `backend/` 中已经部署的机构 ETL、MySQL 客户端、TRSGraph 客户端和 Schema。

## 目录内容

```text
organization_ETL/
├── run_etl.py      # 统一入口：预检、演练、写入、验收
├── run_etl.sh      # 启动脚本，优先使用 backend/.venv/bin/python
├── .env.example    # 可选的独立配置模板
└── README.md       # 本说明
```

实际复用的项目文件包括：

- `backend/script/organization_entity_etl.py`
- `backend/script/organization_relation_etl.py`
- `backend/script/workflows/organization_ingest_workflow.py`
- `backend/script/organization_acceptance.py`
- `backend/script/organization_etl_common.py`
- `backend/schemas/dev_organization_schema.ngql`
- `backend/infra/gkx_element.py`
- `backend/infra/graph_db/`

不要单独复制 `organization_ETL` 到一个没有完整项目的目录；它应保持在 `backend/organization_ETL` 下。

## 配置

入口按以下顺序选择配置：

1. 如果存在 `backend/organization_ETL/.env`，使用它；
2. 否则使用项目现有的 `backend/.env`；
3. 也可以在命令最前面用 `--env-file` 指定其他文件。

如果甲方现有 `backend/.env` 已正确配置以下变量，无需创建新的 `.env`：

```dotenv
GKX_ELEMENT_MYSQL_HOST=MySQL地址
GKX_ELEMENT_MYSQL_PORT=3306
GKX_ELEMENT_MYSQL_DATABASE=gkx_element
GKX_ELEMENT_MYSQL_USERNAME=用户名
GKX_ELEMENT_MYSQL_PASSWORD=密码

TRS_GRAPH_BASE_URL=http://图服务地址:8090
TRS_GRAPH_SPACE=dev
TRS_GRAPH_API_KEY=
TRS_GRAPH_TIMEOUT=60
```

若项目 `.env` 只有 `MYSQL_*`，脚本也会兼容复用；但机构来源数据库名默认固定为 `gkx_element`。建议使用只有 `SELECT` 权限的 MySQL 账号。

## 执行顺序

进入目录：

```bash
cd /data1/zhouwei/guokexin/all/tech-kg-api/backend/organization_ETL
chmod +x run_etl.sh
```

### 1. 预检

```bash
./run_etl.sh preflight --scope all
```

预检只读，不写图。它检查 Python 版本、MySQL 连接、国内外机构39张来源表、32组关系必需字段、TRSGraph 服务和目标空间。

必须看到结果中的：

```json
{"ok": true}
```

如果缺表或缺字段，不要直接正式执行。

### 2. 小样本演练

```bash
./run_etl.sh dry-run --scope all --max-records 10
```

演练会读取真实 MySQL 数据并执行实体转换、关系解析和端点检查，但不会写节点或边。

### 3. 全量演练

```bash
mkdir -p var/log
./run_etl.sh dry-run --scope all \
  > var/log/full_dry_run.json \
  2> var/log/full_dry_run.log
```

不带 `--max-records` 才是全量演练。检查结果中的：

- `failed`
- `invalid`
- `source_missing`
- `target_missing`
- `unresolved_identifier`
- `qualityIssues`

### 4. 正式写入

确认甲方已完成数据库备份或快照后：

```bash
batch="ORG_DELIVERY_$(date -u +%Y%m%dT%H%M%SZ)"
./run_etl.sh write --scope all --ingest-batch "$batch" --yes \
  > "var/log/${batch}.json" \
  2> "var/log/${batch}.log"
```

正式流程自动按顺序执行：

1. 初始化或补齐 `dev` 图 Schema；
2. 写入国内外机构相关实体；
3. 校验端点并写入机构关系；
4. 生成写入前后验收报告。

脚本默认写入 `dev`；显式配置的 `test` 或 `org_etl_test_` 前缀空间可用于隔离测试，正式写入必须提供 `--yes`。

只导入国内或国外时：

```bash
./run_etl.sh write --scope domestic --ingest-batch ORG_DOMESTIC_001 --yes
./run_etl.sh write --scope foreign  --ingest-batch ORG_FOREIGN_001  --yes
```

### 5. 验收

```bash
./run_etl.sh verify > var/log/verify_after.json
```

完整写入产生的验收文件默认位于：

```text
organization_ETL/var/reports/organization/<批次号>_acceptance.json
organization_ETL/var/reports/organization/<批次号>_acceptance.md
```

## 隔离测试空间

入口除 `dev` 外，只允许 `test` 或名称以 `org_etl_test_` 开头的测试空间，防止误写其他业务空间。测试空间需先由图数据库管理员创建，例如：

```ngql
CREATE SPACE IF NOT EXISTS org_etl_test_20260822(vid_type=FIXED_STRING(256), partition_num=10, replica_factor=1);
```

随后显式设置空间并执行：

```bash
export TRS_GRAPH_SPACE=org_etl_test_20260822
./run_etl.sh preflight --scope all
./run_etl.sh init-schema --yes
./run_etl.sh write --scope all --max-records 1 --ingest-batch ORG_TEST_001 --yes
./run_etl.sh verify
```

测试空间不会影响 `dev`。首次小样本按每张表独立取前 N 条，关系行与实体行不一定对应，因此 `source_missing`/`target_missing` 只代表抽样引用不闭合；应结合 `failed`、实际写入数量和全量演练判断。

## 失败后的处理

- MySQL 连接失败：检查地址、端口、账号白名单和 `SELECT` 权限。
- 图服务失败：确认配置的是 `trs-graph-service` HTTP 地址，不是 GraphD 的 9669 端口。
- 缺表/缺字段：先核对甲方 MySQL 数据版本，不要修改映射绕过。
- 中途失败：保留 JSON 和日志，修复后重跑。节点使用稳定 VID，关系使用稳定 identity，可安全幂等重跑。
- 提示已有 ETL 运行：先确认没有其他机构 ETL 进程，再处理 `/tmp/tech_kg_organization_etl.lock`。

退出码：`0` 成功，`1` 运行或写入失败，`2` 预检失败，`3` 存在数据质量告警。
