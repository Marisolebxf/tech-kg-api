# 九个业务服务 API 接口统计

本文按前端 `frontend/src/views/business-service/service-modules.ts` 中配置的九个业务模块统计对应 API。所有接口均挂载在后端 `backend/biz/router/register.py` 的 `/api/v1` 前缀下，并需要登录鉴权。

| 序号 | 业务 key | 业务名称 | 请求方法 | API 接口 |
| --- | --- | --- | --- | --- |
| 1 | `expert-direct` | 科技专家/人才直接关系 | `POST` | `/api/v1/kg-construction/expert-direct-relations/query` |
| 2 | `node-indirect` | 科技单节点间接关系 | `POST` | `/api/v1/kg-construction/expert-indirect-relations/demo/structured-result` |
| 3 | `two-point-achievement` | 科技两点合作成果 | `POST` | `/api/v1/kg-construction/expert-cooperation-achievements/query` |
| 4 | `expert-colleague` | 科技专家同事关系 | `POST` | `/api/v1/kg-service/expert-colleague-relation` |
| 5 | `expert-alumni` | 科技专家校友关系 | `POST` | `/api/v1/kg-construction/expert-alumni-relations/query` |
| 6 | `paper-cooperation` | 科技专家论文合作关系 | `POST` | `/api/v1/kg-construction/expert-paper-cooperation-relations/structured-result` |
| 7 | `enterprise-relation` | 重点关注科技企业关系 | `POST` | `/api/v1/kg-service/key-enterprise-relation` |
| 8 | `industry-chain-event` | 科技产业链点TOP-N事件关系 | `POST` | `/api/v1/kg-service/industry-node-top-events` |
| 9 | `industry-chain-panorama` | 科技产业链全景图 | `POST` | `/api/v1/kg-construction/industry-chain-panorama/query` |

## 后端 Handler 对应关系

| 业务 key | Handler 文件 | Router 前缀/路径 |
| --- | --- | --- |
| `expert-direct` | `backend/biz/handler/expert_direct_relation.py` | `/kg-construction/expert-direct-relations/query` |
| `node-indirect` | `backend/biz/handler/expert_indirect_relation.py` | `/kg-construction/expert-indirect-relations/demo/structured-result` |
| `two-point-achievement` | `backend/biz/handler/expert_cooperation_achievement.py` | `/kg-construction/expert-cooperation-achievements/query` |
| `expert-colleague` | `backend/biz/handler/expert_colleague_relation.py` | `/kg-service/expert-colleague-relation` |
| `expert-alumni` | `backend/biz/handler/expert_alumni_relation.py` | `/kg-construction/expert-alumni-relations/query` |
| `paper-cooperation` | `backend/biz/handler/expert_paper_cooperation.py` | `/kg-construction/expert-paper-cooperation-relations/structured-result` |
| `enterprise-relation` | `backend/biz/handler/tech_enterprise_relation_business.py` | `/kg-service/key-enterprise-relation` |
| `industry-chain-event` | `backend/biz/handler/industry_node_top_events_business.py` | `/kg-service/industry-node-top-events` |
| `industry-chain-panorama` | `backend/biz/handler/industry_chain_panorama.py` | `/kg-construction/industry-chain-panorama/query` |

## 兼容与说明

- `expert-direct` 还提供 `GET /api/v1/kg-construction/expert-direct-relations/query`。
- `industry-chain-panorama` 还提供 `GET /api/v1/kg-construction/industry-chain-panorama/query`。
- `two-point-achievement` 还有 legacy 路由：`/api/v1/kg-service/two-point-achievements`。
- `expert-alumni` 还有 legacy 路由：`/api/v1/kg-service/expert-alumni-relation`。
- 多数模块还提供无路径后缀的 `GET` describe 接口，用于返回模块说明和契约元信息。
