# 超算 GET/POST 接口适配与部署

## 方案与范围

超算入口仅允许 GET、POST。此前配置更新/删除、Schema 来源绑定与删除、任务启停、成员业务绑定等使用 PUT/PATCH/DELETE，会在到达应用前被拦截。

后端为 27 个接口提供显式 POST 操作入口，复用同一处理函数、输入模型、权限依赖、返回结构和业务审计。前端 18 处调用及来源恢复脚本同步迁移。写操作不使用 GET，不使用 X-HTTP-Method-Override，不在失败后自动重试旧方法。

旧 PUT/PATCH/DELETE 路由暂时兼容已有客户端，标记弃用且不再出现在 OpenAPI 文档中；它们在受限入口仍被网关拒绝。本改动不放宽任何安全网关规则。后续待所有调用方迁移后，可另行删除旧路由。当前前端生产 API 请求只使用 GET/POST。

## 接口映射

表中路径相对于 `/api/v1`；超算外部路径按现有部署为 `/bkg_zp/api/v1`。请求体、查询参数（如 LLM `force`）、认证及业务/空间头沿用原接口。脚本替换保持 multipart/form-data 的 `script` 文件字段；删除/解绑 POST 无业务请求体，前端发送 `{}`，配置头仍放 Axios 第三个参数。

| 原接口（兼容期保留） | 推荐接口 |
|---|---|
| PUT `/admin/members/{user_id}/admin` | POST `/admin/members/{user_id}/admin/update` |
| PUT `/business-access/businesses/{client_id}` | POST `/business-access/businesses/{client_id}/update` |
| PUT `/business-access/members/{user_id}` | POST `/business-access/members/{user_id}/update` |
| PUT `/business-access/spaces/{space_name}` | POST `/business-access/spaces/{space_name}/update` |
| PATCH `/corrections/{correction_id}` | POST `/corrections/{correction_id}/update` |
| DELETE `/corrections/{correction_id}` | POST `/corrections/{correction_id}/delete` |
| PUT `/embedding-config/{config_id}` | POST `/embedding-config/{config_id}/update` |
| DELETE `/embedding-config/{config_id}` | POST `/embedding-config/{config_id}/delete` |
| DELETE `/graph-spaces/{space_name}` | POST `/graph-spaces/{space_name}/unbind` |
| PUT `/llm-config/llm-configs/{config_id}` | POST `/llm-config/llm-configs/{config_id}/update` |
| DELETE `/llm-config/llm-configs/{config_id}` | POST `/llm-config/llm-configs/{config_id}/delete` |
| PUT `/manual-reviews/production/{case_id}/draft` | POST `/manual-reviews/production/{case_id}/draft/update` |
| DELETE `/manual-reviews/production/{case_id}` | POST `/manual-reviews/production/{case_id}/delete` |
| PUT `/milvus-configs/{config_id}` | POST `/milvus-configs/{config_id}/update` |
| DELETE `/milvus-configs/{config_id}` | POST `/milvus-configs/{config_id}/delete` |
| PUT `/mysql-datasources/{datasource_id}` | POST `/mysql-datasources/{datasource_id}/update` |
| DELETE `/mysql-datasources/{datasource_id}` | POST `/mysql-datasources/{datasource_id}/delete` |
| DELETE `/schema-management/schemas/{schema_id}` | POST `/schema-management/schemas/{schema_id}/delete` |
| DELETE `/schema-management/schemas/{schema_id}/properties/{property_name}` | POST `/schema-management/schemas/{schema_id}/properties/{property_name}/delete` |
| PUT `/schema-management/schemas/{schema_id}/sources` | POST `/schema-management/schemas/{schema_id}/sources/update` |
| PUT `/schema-management/schemas/{schema_id}/script` | POST `/schema-management/schemas/{schema_id}/script/update` |
| PUT `/task-center/update-policy` | POST `/task-center/update-policy` |
| PUT `/workflow-system/schedules/{schedule_id}/state` | POST `/workflow-system/schedules/{schedule_id}/state` |
| DELETE `/workflow-system/schedules/{schedule_id}` | POST `/workflow-system/schedules/{schedule_id}/delete` |
| PUT `/workflow-system/jobs/{job_id}/state` | POST `/workflow-system/jobs/{job_id}/state` |
| PUT `/workflow-system/jobs/{job_id}` | POST `/workflow-system/jobs/{job_id}/update` |
| DELETE `/workflow-system/jobs/{job_id}` | POST `/workflow-system/jobs/{job_id}/delete` |

图空间 `/unbind` 只解除绑定，不删除图数据库数据。审核批量删除、Schema 脚本校验保存等已有 POST 操作不变。非方法相关的接口行为、权限及用户界面保持原有语义。

## 发布与回退

1. 先部署含新 POST 路由的后端，再部署对应前端；也可在同一发布窗口发布两者。无需数据库迁移或新增环境变量。只部署新前端会在旧后端遇到 404/405。
2. 保持浏览器与 API 同源：超算页面 `/bkg_zp/` 调用 `/bkg_zp/api/`，沿用现有 nginx 代理和运行时配置。不要把 VITE_API_BASE 指到另一来源；JSON 或自定义头的跨域调用需要 OPTIONS，会与当前限制冲突。
3. 不需要因本次路由改动重新部署 worker；若同次发布包含其他 worker 变更，按相应发布要求处理。
4. 先在测试业务/空间验证配置修改/删除、Schema 来源绑定/属性与Schema删除、任务启停/删除、成员业务绑定、空间归属/解绑、审核单条删除。使用专用测试数据，检查审计和真实状态；拒绝越权仍应返回 401/403，资源冲突、无效参数仍按原规则处理。浏览器 Network 中这些请求应为 POST，不应有业务调用引发的 OPTIONS。
5. 回退时先将前端回退，再回退后端，避免新前端调用旧后端。超算限制存在时，回退旧前端会重新暴露原 PUT/DELETE 不可用问题，应暂停相关操作并协调验收窗口；回退不意味着该环境恢复兼容。

已有验收通过的服务按通知排期修改。若本轮验收包含上述操作，应在发布前向项目组明确验收依赖及窗口，不把本地测试通过视为超算现场验收通过。

## 内部依赖与未覆盖边界

本次解决本应用 HTTP 入口的接口兼容。部署前由环境方确认限制的实际位置；不能仅凭外部入口策略推定集群 Service 间也受限。

| 链路 | 现有协议依赖 | 对应处理 |
|---|---|---|
| API/worker → trs-graph | 部分更新 PUT、删除 DELETE | 核对是否经过限制点；若受限，需与图服务方提供的 GET/POST 合同共同改造，不单方面更改调用方法 |
| API/worker/Milvus → S3/RustFS | HEAD、PUT、DELETE及签名 | 标准 S3 协议不能靠本应用机械改成POST；若该链路也被限制，必须由基础设施方确定合规服务链路/存储适配方案后联调，不能宣称本PR已解决 |
| API → Elasticsearch | HEAD 检查、PUT 索引/mapping、DELETE 索引 | 若受限，与搜索服务侧协调兼容操作接口；就绪检查失败可回退图查询，但索引维护/抽取仍需单独验证 |
| API/worker → script sandbox | DELETE 取消运行 | 若受限，需沙箱服务同步提供 POST 取消契约后再迁移客户端 |
| 外部客户端 → 审核附件上传地址 | presigned PUT，完成时 HEAD | 当前前端未使用此入口；外部调用方若使用且路径受限，需联合调整上传方案及对象验证 |

不通过新增公网代理、改写签名请求或伪装方法来规避策略。现场证据应记录部署提交、入口拒绝日志、涉及路径、调用方向及业务结果；不要记录令牌或密钥。健康探测用 GET `/health`，不要用 `curl -I`（HEAD）判断服务不可用。

## 验证

- 前端 `post-operations.spec.ts` 调用真实 API 导出函数并由 Axios adapter 模拟 GET/POST 白名单，覆盖全部18处迁移的 URL、body、query、权限上下文、Cookie和失败不回退。
- 后端 `test_http_post_compat.py` 在完整注册路由上检查27组新旧处理函数/依赖/输入与响应契约，并通过只放行GET/POST的ASGI包装验证认证、授权、配置更新删除及multipart脚本上传。
- 运行相关已有回归、前端类型检查和生产构建；具体执行结果随 PR 记录。
- 本地验证使用隔离容器与测试替身，不涉及超算真实账号、生产数据库写入或现场网关配置变更。
