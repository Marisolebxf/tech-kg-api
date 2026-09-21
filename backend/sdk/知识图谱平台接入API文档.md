# 语义计算工具库系统 API 文档

版本：semantic-toolkit-2026.08 ｜ 更新日期：2026-09-16

---

## 1. 概述

### 1.1 基础信息

| 项 | 说明 |
|---|---|
| Base URL | `http://<服务器地址>/api/v1`（经 nginx）；直连后端为 `http://<服务器地址>:8000/api/v1` |
| 协议 | HTTP / JSON（文件上传为 `multipart/form-data`） |
| 字符编码 | UTF-8 |
| 交互式文档 | `GET /docs`（Swagger UI，实时可用） |

### 1.2 认证

系统支持 API Key 鉴权（**默认关闭**，需服务端配置环境变量 `API_KEYS` 后启用）：

```
X-API-Key: <密钥>
```

- 配置后，除 `/health`、`/docs` 外的全部接口需携带请求头 `X-API-Key`，值为 `API_KEYS`（逗号分隔）中的任一密钥
- 未启用时（默认）所有接口可直接访问

### 1.3 通用响应信封

所有业务接口返回统一信封：

```json
{
  "code": 0,               // 0=成功；422xx=业务校验失败；50001=执行失败
  "message": "success",
  "data": { ... },          // 业务结果（结构随功能点而异）
  "meta": {
    "request_id": "req_...",
    "task_id": "tsk_...",
    "record_id": "rec_...",
    "input_type": "text",   // text / texts / file / files
    "elapsed_ms": 6427,
    "database_dialect": "mysql"
  }
}
```

| code | 含义 |
|---|---|
| 0 | 成功 |
| 42201 | 参数校验失败（缺必填/格式错误/语言不匹配等，message 说明原因） |
| 422xx | 资源校验失败（上传资源缺字段/解析失败） |
| 50001 | 算法执行失败 |

### 1.4 输入模式

19 个功能点统一提供四种输入端点（部分功能点无批量或文件模式）：

| 模式 | 端点后缀 | 请求格式 | 说明 |
|---|---|---|---|
| 单文本 | `/text` | JSON | 一篇文献的文本片段 |
| 批量文本 | `/texts` | JSON | 多篇（数组） |
| 单文件 | `/file` | multipart | 一篇 PDF/DOCX/TXT，服务端解析 |
| 批量文件 | `/files` | multipart | 多篇文件 |

**通用请求字段**（按功能点取用）：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `document_title` | string / string[] | 文本/批量文本模式必填（批量=逐篇题目数组，与文本条数一致） | 文献题目；标识响应结果与可视化弹窗中的当前文献；文件模式由文件名兜底 |
| 主文本字段 | string / object[] | 必填 | 各功能点主输入（`abstract` / `text` / `scientific_document_full_text` / `citation_sentence_and_context` 等） |
| `min_keywords` / `max_keywords` | integer | 选填 | 关键词数量范围（关键词类功能点） |
| 用户上传资源字段 | object / file | **必填（默认内置）** | 资源参数功能必需，不传即使用内置资源；替换为自有时三种给法：**A. multipart 直接带文件**（= 在线测试形态，推荐）；**B. `{"resource_id": "..."}`**（先调资源上传接口）；**C. `{"resource_url": "https://..."}`**（资源在自己的服务器上，直接给地址，系统下载后走同一套校验）。见第 4 节 |

---

## 2. 通用接口

### 2.1 健康检查

```
GET /health
```
返回数据库连接、模型服务状态。

### 2.2 功能点目录

```
GET /api/v1/catalog
```
返回 19 个功能点的编码、名称、输入类型、端点。

### 2.3 文件预解析（引用类工具的 PDF）

```
POST /api/v1/files/parse        # multipart: file
```
上传 PDF → 服务端解析（MinerU）→ 返回 `parse_id`；后续功能点请求携带 `preparsed: "[parse_id]"` 即免重复解析（解析在上传动作完成，点测试后只剩功能执行）。

### 2.4 引用元数据解析

```
POST /api/v1/citation-metadata/parse      # {"entries_text": "参考文献条目原文（每行一条）"}
```
大模型解析参考文献条目为结构化元数据（作者/题名/年份/来源/DOI）。

---

## 3. 用户上传资源接口

### 3.1 资源上传（入库）

```
POST /api/v1/semantic-resources/upload     # multipart: resource_key + upload(.json)
```
- `resource_key`：资源字段名（见第 4 节，如 `clc_labeled_data`）
- 响应返回 `resource_id`，后续功能点请求以 `{"resource_id": "..."}` 引用
- **一次性语义**：在线测试链路中，请求结束后资源自动清理；独立入库的上传不清理

### 3.2 资源预检（选文件即校验，不落库）

```
POST /api/v1/semantic-resources/validate   # multipart: resource_key + upload(.json)
```
返回 `{valid, rows, normalized_by, error}`——上传前即可发现格式问题；预检产生的大模型整理结果落盘复用（同内容提交秒级，不重复调用）。

### 3.3 资源查询

```
GET /api/v1/semantic-resources?resource_key=<字段>&status=current
```

### 3.4 三层容错（全部 11 类资源统一）

```
① 确定性归一：标准字段名 + 中文别名（术语/变体/引用句/类目…）直接折算，秒级通过
② 必要字段探测：语法可解析但缺必要字段 → 明确报错（"缺少必要字段：X。检测到的字段：Y。标准格式：Z"）
③ 大模型结构化重构：字段齐备但结构不规整/语法损坏 → GLM 重构为标准格式 → 重过确定性校验
```

---

## 4. 用户上传资源格式规范（11 类）

| resource_key | 所属功能点 | JSON 格式 | 作用机制 |
|---|---|---|---|
| `clc_labeled_data` | zh/en-classify | 数组：`clc_code`（分类号）+ `clc_name`（类目名）；大表可加 `parent_code` | 答案空间替换：分类号只落用户体系 |
| `classification_standard_mapping_table` | en-classify / en-keyword | 分类工具：`term`（英文术语）+ `zh_term/label`（中文标准表达）；关键词工具：`term` + `clc_code` + `clc_name` | 分类=翻译增强；关键词=逐词分类号确定性覆盖 |
| `domain_classification_rules` | domain-classify | 数组：`clc_code` + `clc_name` + `parent_code`（构成三级树） | 领域类目体系替换 |
| `manually_labeled_training_data` | domain-classify | 数组：`text`（示例文本）+ `label`（分类标签） | few-shot 口径校准 + 相似度覆盖（阈值内跟随用户标注） |
| `domain_terminology_library` | en-keyword | 数组：`canonical`（标准术语）+ `variants`（变体/缩写/同义词） | 候选注入 + 变体归一（normalized_term=canonical） |
| `preprocessed_training_set` | citation-intent | 数组：`document_title` + `document_text`（含引用句）+ `intent`（背景介绍/引入研究方法/结果比较）；`reference_entries` 选填 | few-shot 口径校准 + 双门槛覆盖（内置置信<0.95 且相似度>0.70 跟随用户标注） |
| `general_domain_annotated_corpus` | general-ner | 数组：`text`（示例文本）+ `entities`（`text` 实体词 + `type` 四类之一 PERSON/LOCATION/ORGANIZATION/EVENT） | few-shot 边界与类型口径校准 |
| `multi_domain_scientific_corpus` | research-ner | 数组：`text` + `entities`（`type` 五类之一 METHOD/DATASET/INSTRUMENT/THEORY/TOPIC） | few-shot 识别增强 |
| `manually_labeled_data` | research-ner | 数组：`canonical`（标准中文词）+ `variants`（变体）+ `canonical_en`（标准英文词）+ `type` | 确定性查表归一（mapping_source=用户标准词表，conf=1.0） |
| `ontology_classification_system` | domain-ner | `{"types":[{"code","name","description","examples"}]}` 或平铺数组 | 答案空间替换：实体类型体系整体换成用户的 |
| `domain_labeled_training_data` | domain-ner | 数组：`text` + `entities`（`type` 用本体 code） | few-shot 实体边界教学 |
| `training_samples` | deep-cluster | 数组：`title` + `text` + `category`（人工类目；编号可选） | 锚点引导：语步相似度 ≥0.55 簇名=用户类目，低于阈值回落内置命名 |

**通用说明**：
- 均 仅 `.json`；顶层支持常见包装（`data/records/items/...`）自动解包；字段支持中文别名（术语/变体/引用句/类目/编号…）
- 上传即预检：字段齐全（含别名）直接过；缺必要字段明确报错；结构不规整由大模型重构
- 资源参数必填：不提交该字段 = 使用内置预置资源（默认）；提交即替换为用户的资源
- 三种提交形态（三选一）：
  - **multipart 内联**（在线测试同构，推荐）：`-F "domain_terminology_library=@terms.json"`
  - **resource_id**：`{"resource_id": "res_xxx"}`（先 `POST /semantic-resources/upload` 入库）
  - **resource_url**：`{"resource_url": "https://your-server/xxx.json"}`——直接给资源地址（http/https、≤10MB、.json），系统下载后走相同的归一化/预检/大模型重构兜底

---

## 5. 功能点接口明细

### 5.1 语步识别工具

#### 5.1.1 中文摘要语步识别 `zh-abstract-move`

```
POST /api/v1/move/abstract/zh/text | /texts | /file | /files
```
| 参数 | 必填 | 说明 |
|---|---|---|
| `document_title` | 文本模式必填 | 题目 |
| `abstract` | 必填 | 中文摘要文本 |
| `min_moves` / `max_moves` | 选填 | 语步数范围 |

响应 `data`：`moves`（语步列表：`move_type` 背景/方法/结果/结论…、`text`、`confidence`、位置）。

#### 5.1.2 英文摘要语步识别 `en-abstract-move`

```
POST /api/v1/move/abstract/en/text | /texts | /file | /files
```
参数同上（`abstract` 为英文摘要）。

#### 5.1.3 基金项目语步识别 `fund-move`

```
POST /api/v1/move/fund/zh/text | /texts | /file | /files
```
| 参数 | 必填 | 说明 |
|---|---|---|
| `document_title` | 文本模式必填 | 项目名称亦可 |
| `project_document_text` | 必填 | 基金申请书文本 |

响应 `data`：`moves`（立项依据/研究内容/研究方案…语步与来源树）。

### 5.2 自动分类工具

#### 5.2.1 中文科技文献自动分类 `zh-classify`

```
POST /api/v1/classify/clc/zh/text | /texts | /file | /files
```
| 参数 | 必填 | 说明 |
|---|---|---|
| `document_title` | 文本模式必填 | 题目 |
| `abstract` | 必填 | 中文摘要 |
| `clc_labeled_data` | 内置默认（可上传替换） | 用户中图分类标准（资源，见第 4 节） |

响应 `data`：`classifications`（主分类 `clc_code/clc_name/classification_path/confidence`）、`multilevel_classification_results`、`classification_statistics_table`。

#### 5.2.2 英文科技文献自动分类 `en-classify`

```
POST /api/v1/classify/clc/en/text | /texts | /file | /files
```
| 参数 | 必填 | 说明 |
|---|---|---|
| `document_title` / `abstract` | 必填 | 英文题目/摘要 |
| `clc_labeled_data` | 内置默认（可上传替换） | 用户分类标准 |
| `classification_standard_mapping_table` | 选填 | 映射规则（英文术语→中文标准表达，翻译增强；命中时跨语言映射状态=已映射（用户映射规则命中）） |

响应 `data`：`classifications`、`cross_language_mapping`（跨语言映射块）、`literature_distribution_analysis_report`。

#### 5.2.3 专业领域科技文献分类 `domain-classify`

```
POST /api/v1/classify/domain/text | /texts | /file | /files
```
| 参数 | 必填 | 说明 |
|---|---|---|
| `document_title` / `abstract` | 必填 | |
| `professional_domain` | **必填** | 专业领域（32 大类编码，如 "28"=建筑与土木工程） |
| `domain_classification_rules` | 选填 | 领域类目体系（三级树） |
| `manually_labeled_training_data` | 选填 | 人工标注训练数据 |

响应 `data`：`classifications`（三级类目）、`domain_match_result`、`training_data_effect`（训练集覆盖时非空）。

### 5.3 关键词识别工具

#### 5.3.1 中文科技文献关键词识别 `zh-keyword`

```
POST /api/v1/keywords/zh/text | /texts | /file | /files
```
| 参数 | 必填 | 说明 |
|---|---|---|
| `document_title` / `abstract` | 必填 | |
| `custom_dictionary` | 内置默认（可上传替换） | 用户词典：`{dictionary_name, weight_boost(0~0.5), terms[]}`——命中词加权并标 `custom_dictionary_hit` |
| `min_keywords` / `max_keywords` | 选填 | 默认 5~8 |

响应 `data`：`keywords`（`keyword/normalized_term/weight/confidence/rank/custom_dictionary_hit`）。

#### 5.3.2 英文科技文献关键词识别 `en-keyword`

```
POST /api/v1/keywords/en/text | /texts | /file | /files
```
| 参数 | 必填 | 说明 |
|---|---|---|
| `document_title` / `abstract` | 必填 | 英文 |
| `domain_terminology_library` | 选填 | 领域术语库（变体注入与归一） |
| `classification_standard_mapping_table` | 选填 | 分类标准映射表（term+分类号，逐词确定性覆盖） |

响应 `data`：`keywords`（含 `normalized_term` 归一形式、`terminology_source`（领域术语库=用户资源命中）、`classification_mapping`（`mapping_engine`=user_resource_direct/user_resource_index/内置检索））。

### 5.4 研究问题识别 `rq-detect`

```
POST /api/v1/research-question/text | /texts | /file | /files
```
| 参数 | 必填 | 说明 |
|---|---|---|
| `document_title` / `text` | 必填 | 全文或摘要 |

响应 `data`：`research_question_sentences`（问题句）、`research_question_phrases`（问题短语）、`structured_research_questions`（规范化问题）、`research_question_statistics`。

### 5.5 引用句识别工具

#### 5.5.1 引用情感识别 `citation-sentiment`

#### 5.5.2 引用意图识别 `citation-intent`

```
POST /api/v1/citation-intent/text | /texts | /file | /files
     （情感识别为 /api/v1/citation-sentiment/...）
```
| 参数 | 必填 | 说明 |
|---|---|---|
| `document_title` | 文本模式必填 | 题目 |
| `scientific_document_full_text` | 必填 | 文献全文（引用句自动抽取） |
| `reference_entries` | **选填** | 参考文献原始条目（每行一条）；提供时解析为被引文献元数据作判定辅助，不填功能照常 |
| `citation_sentence_and_context` | 选填 | 手动提供引用句及上下文（高级路径；默认自动派生） |
| `preprocessed_training_set` | 内置默认（可上传替换，仅意图工具） | 训练集（few-shot 口径校准 + 双门槛覆盖） |

响应 `data`：`citation_intent_results`（`citation_sentence`、`intent`（背景介绍/引入研究方法/结果比较）或 `sentiment`（支持/中立/有局限性）、`confidence`、`context`、`training_data_effect`（训练集覆盖时非空，含命中样本与相似度））。

### 5.6 概念定义句识别 `definition-detect`

```
POST /api/v1/concept-definition/text | /texts | /file | /files
```
| 参数 | 必填 | 说明 |
|---|---|---|
| `text` | 必填 | 全文（定义句在正文） |
| `domain_label` | 选填 | 领域标签（默认自动识别） |

响应 `data`：`definitions`（概念词/定义句/置信度/位置）、`concept_definition_mappings`、`statistics`。

### 5.7 命名实体识别工具

#### 5.7.1 通用实体识别 `general-ner`

```
POST /api/v1/ner/general/text | /texts | /file | /files
```
| 参数 | 必填 | 说明 |
|---|---|---|
| `document_title` / `text` | 必填 | |
| `general_domain_annotated_corpus` | 选填 | 标注语料（few-shot 边界与类型口径） |

响应 `data`：`entity_results`（`text/type`（PERSON/LOCATION/ORGANIZATION/EVENT）/`confidence/start/end/context`）。

#### 5.7.2 科研实体识别 `research-ner`

```
POST /api/v1/ner/research/text | /texts | /file | /files
```
| 参数 | 必填 | 说明 |
|---|---|---|
| `document_title` / `text` | 必填 | |
| `multi_domain_scientific_corpus` | 选填 | 科研语料（few-shot） |
| `manually_labeled_data` | 选填 | 标准词表（变体→标准词确定性归一） |

响应 `data`：`entity_results`（含 `standard_names{zh,en}`、`mapping_status`（已映射（用户上传资源命中）/内置映射/未映射）、`mapping_confidence`（用户词表=1.0））。

#### 5.7.3 专业实体识别 `domain-ner`

```
POST /api/v1/ner/domain/text | /texts | /file | /files
```
| 参数 | 必填 | 说明 |
|---|---|---|
| `document_title` / `text` | 必填 | |
| `domain` | 选填 | 专业领域（医学/药学/化学/化工/物理/生物/计算机/材料/农业/环境/地学）——实体领域标签与类型体系跟随；不选=自动识别 |
| `ontology_classification_system` | 内置默认（可上传替换） | 用户本体（答案空间替换：类型体系整体换成用户的） |
| `domain_labeled_training_data` | 选填 | 领域训练数据（实体边界教学） |

响应 `data`：`entity_results`（`type`=本体 code 或领域专属类型；`standard_kb_id`=用户本体体系/内置知识库）、`selected_domain`。

内置领域类型体系（未传本体时按领域生效，节选）：医学→DRUG/DISEASE/TREATMENT/SYMPTOM/MEDICAL_DEVICE；计算机→ALGORITHM/MODEL/DATASET/FRAMEWORK/METRIC/TASK；生物→PROTEIN/GENE/CELL/ORGANISM/PATHWAY/TECHNIQUE…（11 领域 57 类全表见 `rules/ner/domain_type_systems.json`）。

#### 5.7.4 实体关系识别 `relation-extract`

```
POST /api/v1/relation/file | /files    （另有 /api/v1/ner/relation 内部端点）
```
| 参数 | 必填 | 说明 |
|---|---|---|
| `file` | 必填 | 含实体标注的文献（或上游 NER 结果） |

响应 `data`：`relation_triples`（三元组）、`dependency_parse`、`knowledge_network`。

### 5.8 深度聚类工具 `deep-cluster`

```
POST /api/v1/cluster/deep/texts | /files | /collection
```
| 参数 | 必填 | 说明 |
|---|---|---|
| `documents` | 文本模式必填 | `[{document_id, text}]` |
| `document_metadata` | 必填 | 逐篇 `[{document_id, title, publication_date}]` |
| `cluster_dimension` | 选填 | `technical`（技术路线，默认）/ `application`（应用场景） |
| `cluster_count` | 选填 | 指定簇数（默认自动） |
| `training_samples` | 选填 | 锚点（`title+text+category` 单文件）——语步相似度 ≥0.55 时簇名=用户类目 |

响应 `data`：`clusters`（`topic_name/size/members/representative_terms/feature_statistics`）、`document_assignments`、`semantic_projection`（二维投影坐标）、`theme_trend_analysis`（年度趋势）、`clustering_quality`。

### 5.9 聚类标签生成 `cluster-label`

```
POST /api/v1/cluster-labels/generate | /texts | /files
```
| 参数 | 必填 | 说明 |
|---|---|---|
| `cluster_task_id` | 选填 | 上游深度聚类任务 ID（沿用其簇结构） |
| `label_language_type` | 选填 | 标签语言（auto/zh/en） |
| `distinctiveness_threshold` | 选填 | 标签区分度阈值 |

响应 `data`：`labels`（簇标签与区分度优化结果）。

### 5.10 结构化自动综述 `structured-review`

```
POST /api/v1/review/structured/texts | /collections
```
| 参数 | 必填 | 说明 |
|---|---|---|
| `topic_or_keywords` | 必填 | 综述主题或关键词 |
| `document_set` | 必填 | 文献集（数据库集合或文献数组） |
| `document_metadata` | 选填 | 文献元数据（题名/作者/年份/来源，多格式） |

响应 `data`：`tree`（综述树）、`cluster_induction_results`、`trend_hotspot_distribution`、`structured_report`。

---

## 6. 调用示例

### 6.1 中文摘要语步识别（JSON）

```bash
curl -X POST "http://<host>/api/v1/move/abstract/zh/text" \
  -H "Content-Type: application/json" \
  -d '{
    "document_title": "深度学习驱动的桥梁损伤识别研究",
    "abstract": "桥梁结构健康监测是保障基础设施安全的重要手段。本文提出一种基于卷积神经网络的损伤识别方法。实验表明所提方法的F1指标达到0.92。研究表明深度学习在结构监测领域具有广阔前景。"
  }'
```

### 6.2 英文关键词识别 + 用户术语库（multipart 内联资源）

```bash
curl -X POST "http://<host>/api/v1/keywords/en/text" \
  -F "document_title=Bridge SHM with CNN" \
  -F "abstract=This paper develops a CNN autoencoder for bridge SHM..." \
  -F "domain_terminology_library=@terminology.json;type=application/json"
```
其中 `terminology.json`：
```json
[{"canonical": "structural health monitoring", "variants": ["SHM"]},
 {"canonical": "convolutional neural network", "variants": ["CNN"]}]
```

### 6.3 两步调用（先入库资源，再 JSON 请求引用）

```bash
# ① 上传资源（得 resource_id）
RID=$(curl -s -X POST "http://<host>/api/v1/semantic-resources/upload" \
  -F "resource_key=ontology_classification_system" \
  -F "upload=@medical-ontology.json;type=application/json" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['resource_id'])")

# ② 功能点请求引用
curl -X POST "http://<host>/api/v1/ner/domain/text" \
  -H "Content-Type: application/json" \
  -d "{
    \"document_title\": \"临床用药安全\",
    \"text\": \"阿司匹林等非甾体抗炎药常用于类风湿关节炎的对症治疗...\",
    \"domain\": \"医学\",
    \"ontology_classification_system\": {\"resource_id\": \"$RID\"}
  }"
```

### 6.4 深度聚类（锚点引导）

```bash
curl -X POST "http://<host>/api/v1/cluster/deep/texts" \
  -H "Content-Type: application/json" \
  -d '{
    "documents": [{"document_id": "DOC001", "text": "..."}, ...],
    "document_metadata": [{"document_id": "DOC001", "title": "...", "publication_date": "2025-01-01"}, ...],
    "cluster_dimension": "technical",
    "training_samples": {"resource_id": "<锚点资源ID>"}
  }'
```

---

## 7. 约定与限制

| 项 | 说明 |
|---|---|
| 文本长度 | 摘要类建议 ≤8000 字；NER/引用全文超 10000 字自动截取前段 |
| 文件格式 | PDF / DOCX / TXT（≤50MB；批量 ≤20 篇） |
| 资源格式 | 仅 `.json`；CSV/JSONL 暂不支持 |
| 一次性资源 | 在线测试链路的内联资源请求后自动清理；独立上传入库的资源持久保留 |
| 并发 | 批量任务内部并发受 GLM 配额控制；大批量建议异步（请求体 `"async": true`，经任务接口轮询） |
| 语言校验 | 中文功能点输入疑似英文（或反之）返回 42201 语言不匹配 |


---

# 知识图谱平台接入指南（v1.0 · 2026-09-21）

## A. 图谱构建映射

| 图谱元素 | 工具 | 端点 | 输出字段 |
|---|---|---|---|
| **节点（科研实体）** | 科研领域命名实体识别 | `POST /ner/research/text` | `data.entities[]`：text(实体)、type(五类 METHOD/DATASET/INSTRUMENT/THEORY/TOPIC)、std_zh/std_en(标准词)、position |
| **节点（通用实体）** | 通用领域命名实体识别 | `POST /ner/general/text` | `data.entities[]`：PERSON/LOCATION/ORGANIZATION/EVENT |
| **节点（领域实体）** | 专业领域命名实体识别 | `POST /ner/domain/text` | 本体类型体系（用户可上传本体限定）|
| **边（三元组）** | 实体关系识别 | `POST /relation/from-ner-record` | `data.triples[]`：subject/relation/object/trigger/dependency_path/sentence_id/source_position |
| **节点属性（分类）** | 中文/英文/专业领域分类 | `POST /classify/{clc/zh|clc/en|domain}/text` | `classifications[]`：clc_code/label/classification_path/confidence |
| **节点属性（关键词）** | 中/英文关键词识别 | `POST /keywords/{zh|en}/text` | `keywords[]`：keyword/normalized_term/classification_mapping |
| **上下文（研究问题）** | 研究问题识别 | `POST /research-question/text` | 三级数组（句/短语/结构化）+ source_sections 溯源 |
| **上下文（引用关系）** | 引用意图/情感识别 | `POST /citation-{intent|sentiment}/text` | citation_intent_results[]：citation_marker/intent |

## B. 标准接入流水线

```
文献 → [1] NER（科研/通用/领域）→ 实体入图谱节点（std_zh 作规范名，position 作证据锚点）
     → [2] relation/from-ner-record（消费 [1] 的 meta.record_id）→ 三元组入边
     → [3] classify_*（节点打领域标签）+ keywords_*（节点属性）
```

**关键依赖**：[2] 必须传 [1] 响应 `meta.record_id`（一次性凭证，测试后即失效）。

## C. Python SDK（semantic_toolkit_kg.py）

零依赖（仅 requests），随本文档交付。核心用法：

```python
from semantic_toolkit_kg import SemanticToolkit, SemanticToolkitError

kg = SemanticToolkit("http://<服务地址>:8000")

# 节点：实体
ner = kg.ner_research(text="Zhang等提出的深度学习方法应用于桥梁监测。")
for ent in kg.entities_of(ner):          # [{text, type, std_zh, std_en, position}, ...]
    graph.add_node(ent["std_zh"] or ent["text"], type=ent["type"])

# 边：三元组（消费上游 record_id）
rel = kg.relation_extract(record_id=kg.record_id(ner))
for t in kg.triples_of(rel):             # [{subject, relation, object, trigger, ...}, ...]
    graph.add_edge(t["subject"], t["object"], label=t["relation"])

# 属性：分类与关键词
cls = kg.classify_zh("桥梁健康监测摘要…", title="题目")
kws = kg.keywords_en("We propose CNN for SHM of bridges.")

# 文件模式（PDF/DOCX/TXT 自动解析）
ents2 = kg.entities_of(kg.ner_general_file("paper.pdf"))

# 批量聚类（≥4 篇）/ 综述（≥2 篇）
clu = kg.deep_cluster(documents=[{"document_id": "d1", "title": "…", "text": "…",
                                  "publication_date": "2024-01-01"}, ...])   # ≥4 篇
rev = kg.structured_review("桥梁监测", documents=[...])                        # ≥2 篇

# 用户资源（术语库/映射表/训练集）先上传后随请求携带 resource_id
lib = kg.upload_resource("domain_terminology_library", "terms.json")

# 错误处理：所有失败抛 SemanticToolkitError（.status_code/.response 可查）
try:
    kg.classify_en("texto en español…")
except SemanticToolkitError as e:
    print(e)  # 不支持非中英文文本：…
```

## D. 接入约束速查

| 约束 | 说明 |
|---|---|
| 文本语言 | 仅中/英文；西班牙语等其他语言明确报错（42201）|
| 文件格式 | 主文献仅 PDF/DOCX/TXT；用户资源仅 JSON（按各资源槽字段约定）|
| 文件大小 | 单文件 ≤50MB；批量 ≤20 个（深度聚类 ≥4、综述 ≥2、其余 ≥2）|
| 损坏文件 | 二进制伪装/乱码/空文件/扩展名不符 → 422 明确报错 |
| 基金语步 | 仅接受基金申请书/进展/结题类文档，普通论文报错 |
| 响应信封 | `{code, message, data, meta}`；code=0 成功，错误信息在 message/error_summary |
| 一次性资源 | 在线测试上传的资源随请求结束清理；API 重复使用请先 upload_resource 取 resource_id |

## E. 异步与进度（批量任务）

批量（texts/files ≥2）可加请求头 `Prefer: respond-async`：立即返回 `{data: {task_id}}`，
轮询 `GET /tasks/{task_id}/progress` 至终态，再 `GET /tasks/{task_id}/vue-result` 取
与同步路径完全一致的结果（可视化弹窗同构）。
