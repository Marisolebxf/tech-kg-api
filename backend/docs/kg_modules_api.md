# KG 构造模块 API

模块说明接口仍为各模块根路径的 `GET`；以下执行接口统一使用 `POST` 并返回 `ApiResponse`。

| 模块 | 执行接口 | 数据来源与结果 |
| --- | --- | --- |
| 专家间接关系 | `/api/v1/kg-construction/expert-indirect-relations/query` | 图数据库两跳路径；排除直接邻居，按路径数和中介节点数评分 |
| 两点合作成果 | `/api/v1/kg-construction/expert-cooperation-achievements/query` | 共同论文、专利、项目；返回分类计数、证据标题和合作评分 |
| 专家同事关系 | `/api/v1/kg-construction/expert-colleague-relations/query` | 当前机构和工作经历中的共同机构证据 |
| 专家校友关系 | `/api/v1/kg-construction/expert-alumni-relations/query` | 教育背景中的共同院校证据 |
| 产业链 TOP-N 事件 | `/api/v1/kg-construction/industry-chain-topn-event-relations/query` | 产业资讯按关键词与时效评分；`persist=true` 时写入 `IndustryEvent` 和 `HAS_EVENT` |
| 产业链全景 | `/api/v1/kg-construction/industry-chain-panorama/query` | 聚合链节点、企业、产品、专利和事件，返回统一点边图 |

专家标识优先使用 `scholar_id`；名称只有在唯一精确匹配时才接受。产业链接口要求 `chainCode` 或 `keyword` 至少提供一个。

事件持久化要求目标产业链节点已经存在于图空间。图服务错误统一映射为 HTTP `502`。
