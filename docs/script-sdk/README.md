# 抽取脚本 SDK 文档（静态站点）

Readthedocs 风格的纯静态文档站，零依赖、无需构建 —— 直接用浏览器打开 `index.html` 即可：

```bash
open index.html
# 或起个本地服务（推荐，相对路径更稳）：
python3 -m http.server 8099 --directory docs/script-sdk
# → http://localhost:8099
```

## 页面结构

| 页面 | 内容 |
| --- | --- |
| `index.html` | 概述、能力地图、快速上手、设计原则、路线图 |
| `context.html` | kg_sdk.Context：五类客户端、watermark、双入口约定 |
| `reading.html` | `iter_rows` 分页（OFFSET/keyset）、`apply_since` 增量、水位闭环 |
| `values.html` | 两套值语义（机构域/原文域）、数值与 JSON 处理 |
| `identity.html` | VID 公式、稳定键、边 rank、端点解析器 |
| `provenance.html` | 溯源属性、三个构造器、置信度打分 |
| `entities.html` | EntityRecord、merge 保护、None 丢弃与字符串化 |
| `relations.html` | EdgeRecord、rank/merge 双通道、端点验存、schema 幂等补齐 |
| `runners.html` | 抽取主流程、summary 口径、双入口模式、CLI 参数 |
| `examples.html` | 三个真实脚本剖析 + 新脚本自查清单 |
| `reference.html` | 全量 API 速查表 + 常见错误对照 |

文档内容以 `backend/script/entity_extractors_one_entity/common.py`、
`backend/script/relation_extractors_one_relation/common.py`、`backend/sdk/kg_sdk.py`
的当前实现为准；「路线图」小节列的是已识别未实施项（双入口框架、共享底层模块、
ctx 注入版 utils、观测式访问溯源）。

改样式调 `assets/style.css`；各页共享同一份侧栏导航，新增页面需同步更新所有页面的 `<nav>` 块。
