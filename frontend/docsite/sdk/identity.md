# 标识与值语义

> 来源：`docs/script-sdk/identity.html` · `docs/script-sdk/values.html`

确定性标识是整个抽取体系的根基：**同一条源数据，任何时候重跑都得到同一个点/同一个身份**。

## 为什么标识必须确定性

所有写入都走 upsert（`merge_node` / 带 rank 的 `INSERT EDGE` / `merge_edge`），upsert 的匹配键来自 VID/rank——如果两次运行对同一行源数据算出不同的 ID，就会产生重复点/边，而不是覆盖更新：

```python
vid = f"person_{uuid4()}"        # ❌ 每次都新点，重跑即翻倍
vid = f"person_{row_index}"      # ❌ 顺序变了 ID 就漂
vid = f"person_{scholar_id}"     # ✅ 源主键 → 稳定
vid = person_vid(kind, org, name, birth, country)  # ✅ 复合身份哈希 → 稳定
```

## 顶点 VID 公式

内置各实体族的公式（`script/entity_extractors_one_entity/common.py`）：

| 函数 | 公式 | 用于 |
|---|---|---|
| `organization_vid(org_id)` | `org_{org_id}` | Organization 点、边端点 |
| `project_vid(project_id)` | `project_{project_id}` | Project |
| `news_vid(record_id)` | `news_{record_id}` | News |
| `event_vid(table, record_id)` | `event_{table}_{record_id}` | Event（表名入键，不同表同名事件不撞） |
| `datasource_vid(table)` | `ds_{table}` | DataSource 点 |
| `person_vid(kind, *identity)` | `person_{md5(kind\|org\|name\|birth\|country)}` | 机构角色 Person（无源主键，复合身份哈希） |
| `product_vid(name)` | `product_{md5(NFKC+casefold(name))}` | Product（按名哈希） |
| `md5_vid(prefix, value, short=True)` | `{prefix}_{md5(normalize_key(value))[:16]}` | 自定义族 |

有源主键的实体直接拼前缀；无主键的（机构角色自然人、产品）用复合身份哈希。`person_vid` 各分量先 NFKC + casefold 再 `|` 连接：

```python
person_vid("shareholder", org_id, name, birth_date, country)
# = 'person_' + md5("shareholder|org123|张三|1970-01-01|CN")
```

论文/学者域是直接拼接（`person_{scholar_id}`、`paper_{paper_id}`）——两个域的 Person 点靠 `--source` 通道区分，互不冲突。

### bounded_vid：64 字节安全阀

NebulaGraph 固定长度字符串 VID 上限 **64 字节**。所有 VID 公式最后都过一道 `bounded_vid`：超限则按字节截断并附加全文 md5 后缀，保证截断后仍然唯一且确定。自定义公式源主键可能超长（复合键、URL、UUID 拼接）时，**务必套一层 `bounded_vid(...)`**。

## 行级稳定键与边 rank

```python
stable_record_id(table, row, preferred_fields=()) -> str
# 复合键字段全非空 → "a|b|c"；否则整行排序 JSON 的 md5 兜底

edge_rank(edge_type, source_vid, target_vid, source_record_id) -> int
# sha256 前 8 字节大端 → 63 位正整数；同一源记录重跑 → 同一 (type, src, dst, rank)
```

归一化基础件：`md5_hex(value)`、`normalize_key(value)`（NFKC + 空白折叠 + casefold）、`clean_text(value)`。**凡参与哈希的文本一律先归一**，否则全角/半角、大小写差异会造出两个"不同"实体。

## 两套值语义口径（显式共存）

历史脚本对「空值」有两种约定，数据已在图里，改口径会造成脏数据，因此两套都保留、命名区分：

| 口径 | 空值行为 | 使用域 | 代表函数 |
|---|---|---|---|
| 机构域口径 | 空白 → `None`（写图时省略该属性） | Organization / Event / News / Product / 机构角色 Person | `text_or_none` |
| 原文口径 | `value or ""`，保留原文 | 学者 / 论文 / 项目 / 专利 | `text_or_empty` |

**不要混用**：同一实体的属性族必须用同一套口径，否则 merge upsert 时会把另一套口径写的值当成「空」覆盖或跳过。拿不准时看同域既有脚本的 mapper。

### 文本语义

```python
text_or_none(value, max_length=20000)  # 机构域：strip、空白→None、超长截断
clean_text(value)                       # 内部键/VID 计算：strip + 折叠空白，不作展示属性
text_or_empty(value)                    # 原文域：str(v) if v else ""
str_or_empty(value)                     # 专利域：仅 None→""，0/False 保留
paper_text(value)                       # 论文域：text_or_empty + 换行转空格
date_text / datetime_text               # 项目/专利域：日期 → ISO 文本

text_or_empty(" 张三 ")  # ' 张三 ' —— 原样保留
text_or_none(" 张三 ")   # '张三' —— strip
text_or_none(" ")        # None —— 空白视为缺失
```

### 数值语义

```python
to_float_or_none("1,200.5万")  # None —— 清洗后无法解析则放弃，不猜
to_float_or_none("1,200.5")    # 1200.5 —— 去千分位逗号
to_float_or_none("-")          # None —— '-','n/a','null','none' 视为缺失
to_float_or_none(float("nan")) # None —— NaN/Inf 一律 None
to_float_or_none(True)         # None —— bool 不当数字
to_float_or_zero(v)            # 项目域：非法 → 0.0
```

### JSON 处理

```python
parse_json(value)     # 字符串尝试 json.loads，失败原样返回（专利域源字段）
original_text(value)  # JSON 数组各元素 text/content 换行连接
extra_json(row)       # 整行源数据快照（json_safe + sort_keys）
bounded_json(value, max_length=64000)
# 机构域安全阀：超长不硬截断，降级为审计摘要
# {"original_length":180000,"preview":"...","sha256":"ab12…","truncated":true}
```

### 字段候选链

同一语义在不同源表里字段名不同（机构 ID 有 7 种写法），用候选链取第一个非空：

```python
org_id = first_value(row, "organization_id", "org_id", "company_id", "entity_eid")
# 机构 ID 标准候选链已固化为 ORGANIZATION_ID_FIELDS + organization_id_from_row(row)
```

### 新脚本怎么选口径

| 你的实体/关系属于 | 文本 | 数值 | extra_json |
|---|---|---|---|
| 机构域（Organization/Event/News/Product/机构角色 Person） | `text_or_none` | `to_float_or_none` | `bounded_json`（merge 保护下多源累积） |
| 学者 / 论文 / 项目 | `text_or_empty` / `paper_text` | `to_float_or_zero` | `extra_json`（整行快照） |
| 专利 | `str_or_empty` / `original_text` / `json_snapshot` | 同上 | `extra_json` |
