# 实体列表文字查询部署与验证

原查询使用 `LOOKUP` 枚举标签后对 `keys(properties(v))` 逐项执行包含过滤。
标签有普通索引也无法让这个过滤直接命中属性文字索引；每次搜索先逐标签
COUNT，再读取分页，冷查询会重复扫描大量节点。

## 新查询行为

- 完整名称和 ID：只索引名称候选字段、`id`、`entity_id` 和 VID 的完整值。
  论文使用 `title_zh`、`title_en` 等名称字段；列表显示优先使用 `title_zh`。
  查询通过 `ix_literal_field_exact(generation, exact_hash, field_name, document_id)`
  定位，并核验完整值，不遍历其他公共属性。大小写不敏感。
- 无完整名称/ID命中：公共属性、名称和 ID 走 1/2/3 字符倒排索引。
  使用至多 8 个字符片段交集筛选候选，再用二进制排序规则下的 `INSTR`
  核验同一个属性值的真实包含关系。中文单字、两字、标点、`%`、`_`、
  引号均按字面匹配，不使用语义近邻补齐结果，也不限制在前 1000 个实体内。
  属性索引保存原始完整值，不使用展示字段或 embedding 的截断文本。
- 分页按实体类型、VID、记录 ID 排序；一实体的多个匹配属性只返回一行。
  同 VID 的不同标签按不同类型展示，与原实体列表一致。
- `/keyword` 只读取 `limit + 1` 条以确认是否还有下一页，不等待完整总数。
  首页面不足一页时可以直接确认总数，否则 `total=null`、`totalStatus=pending`。
  前端先显示本页和“统计中”，再独立调用 `/keyword/count` 更新真实总数。
  统计期间可以翻页；统计失败保留数据并可重新统计；查询切换或离开页面
  会取消统计请求。统计接口执行同步数据库查询，不持有已关闭的后台 Session。
- 每次发布或增量写入都会更新 revision；统计请求携带分页返回的
  `generation`（对外的 revision）和 `matchMode`，过期版本要求重新查询。
  现有 `/search` 语义检索和空关键词 `/entities` 浏览接口保留。

索引使用已有 `WORKFLOW_MYSQL_*` 控制库，新增四张 `kg_entity_literal_*` 表；
不新增 Elasticsearch 服务，也不依赖 Milvus、embedding 或 BM25 重建。
倒排键使用二进制 SHA-256；完整值核验确保哈希冲突不会产生错误匹配。

## 首次部署

1. 为 API、worker 和写图脚本配置同一 `WORKFLOW_MYSQL_*` 控制库；保持
   `ENTITY_LITERAL_INDEX_SYNC_ENABLED=true`（默认 true）。账号需要索引表的
   建表和读写权限。所有节点写入进程都需要部署本次 `TRSGraphClient` 改动。
2. 从 `backend` 目录为每个要使用实体搜索的空间构建一次文字索引：

   ```bash
   PYTHONPATH=. python -m script.build_entity_literal_index --space dev2
   ```

   将 `dev2` 换为实际空间名。大空间构建应安排在维护窗口：构建与受支持的
   节点写入使用同一 MySQL advisory lock，构建期间写入最多等待 60 秒后报错；
   已发布的旧索引可继续查询。首次建索引期间搜索会明确提示索引未就绪。
3. 命令成功输出 `generation`、各类型数量和 `total` 后部署/刷新前端。
   任一标签枚举失败、跳过、重复主键或数据库写入失败都不会发布部分索引；
   保留上一个已发布版本。普通标签索引仍用于构建阶段的全图枚举；应先补建
   缺失的图标签索引，再重新执行命令。

## 更新与一致性

`create_node`、`merge_node`、`update_node`、`delete_node`、`batch_create_nodes`
以及图谱构建、人工审核和置信度写回使用的 `execute_entity_write(query, node_ids=[...])`
在图写成功后更新文字索引，并刷新类型计数与 revision。每次图写前先提交
索引失效标记，所有索引更新完成后再恢复 ready；中途进程退出或同步失败
都不会让未维护的旧索引继续作为当前结果返回。图写已成功、索引同步失败时
记录日志、保留图写结果，搜索提示重建索引。

`execute_query` / `execute_write` 中的原始节点增删改、修改/删除 TAG、
删除 SPACE 会令索引失效，必须重新运行构建命令。原始查询无法可靠解析
全部受影响 VID；有明确 VID 的调用应改用 `execute_entity_write`，该路径会从
图库读回完整节点并增量维护索引（删除节点则移除索引记录）。关系写入、读查询、索引 DDL、STATS 任务不会因此失效。
绕过本仓库客户端的外部直接导入/修改也需要重新构建；索引不是外部写入的 CDC。
构建时必须暂停这类不参与 advisory lock 的外部写入。

旧 generation 暂不自动删除，以免影响正在读取旧版本的请求。失败构建的
本次 generation 会清理；重复全量重建产生的历史数据需在维护窗口、确认
无构建和在途查询后清理。容量规划应计入字段数、文本长度和字符片段数量。

## 验证与性能边界

单元测试覆盖完整标题、业务 ID/VID、单字/短语、字面标点、长属性末尾、
候选交集后核验、重复匹配去重、跨空间隔离、1015 条分页、独立计数、
构建失败回滚及增量同步失败。API 测试检查权限、输入校验和过期 revision；
前端测试检查慢统计时先显示数据、翻页不重复统计、旧请求取消及统计失败重试。

本次本地验证使用 SQLite 索引表和模拟图服务，未连接部署中的 MySQL/TRSGraph，
不声称生产查询耗时或亿级容量已经验证。上线前应在代表性数据上使用 MySQL
`EXPLAIN ANALYZE` 验证完整名称走 `ix_literal_field_exact`，包含查询走倒排主键；
测量本页响应和 COUNT 的各自耗时、索引容量与增量写入耗时。常见单字、极宽泛
关键词及深 OFFSET 仍可能处理大量候选；独立 COUNT 解除的是首屏等待，
并不消除这些查询本身的成本。
