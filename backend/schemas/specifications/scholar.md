# 人才专家数据表规范

本规范依据第三方最新字段清单整理。DDL 中的表名、字段名、字段长度和字段含义以本文件为准。

## 类型映射约定

| 第三方类型 | MySQL 类型 |
|---|---|
| 字符型，长度不超过 4096 | `VARCHAR(n)` |
| 字符型，长度 65535 | `TEXT` |
| 文本型 | `TEXT` |
| 数字型，精度 8 | `BIGINT` |
| 数字型，精度 1 | `TINYINT` |
| 日期型 | `DATETIME`；仅包含日期的业务字段使用 `DATE` |

> 第三方规范没有提供是否为空、默认值、主键、唯一键和外键信息，因此当前 DDL 不擅自增加这些约束。后续拿到数据质量规则后再补充。

## 1. 学者 `dwd_scholar`

| 字段中文名称 | 字段英文名称 | 数据类型 | 长度 | 字段描述 | 数据样例 |
|---|---|---:|---:|---|---|
| 学者ID | `scholar_id` | 字符型 | 32 | 学者记录的业务唯一标识 | `accc1946` |
| 英文姓名 | `name_en` | 字符型 | 128 | 学者的英文姓名 | `Weinan E` |
| 中文姓名 | `name_zh` | 字符型 | 128 | 学者的中文姓名 | `鄂维南` |
| 头像 | `avatar` | 字符型 | 256 | 学者头像图片的访问链接 | `https://cdn1.deepmd.net/static/img/cc7e320faccc1946.png` |
| 英文机构 | `scholar_org_name_en` | 字符型 | 4096 | 学者所属机构的英文名称 | `Professor of Mathematics, Princeton University` |
| 中文机构 | `scholar_org_name_zh` | 字符型 | 1024 | 学者所属机构的中文名称 | `普林斯顿大学数学系;北京大数据研究院;北京大学数学科学学院计算数学教研室` |
| 个人简介/学术简介 | `bio` | 文本型 | - | 学者的个人或学术简介信息 | `The scholar's main research interests span applied mathematics, computational science, and machine learning.` |
| 中文个人简介/学术简介 | `bio_zh` | 文本型 | - | 学者的中文个人或学术简介信息 | `该学者主要研究方向横跨应用数学、计算科学与机器学习领域。` |
| 英文工作经历 | `work_experience_en` | 文本型 | - | 学者英文工作经历信息 | `2021-Present: Professor, School of Mathematical Sciences, Peking University` |
| 中文工作经历 | `work_experience_zh` | 文本型 | - | 学者中文工作经历信息 | `2021年至今：北京大学数学科学学院 教授` |
| 英文教育背景 | `education_background_en` | 文本型 | - | 学者的英文教育经历信息 | `Ph.D. Mathematics UCLA 1989` |
| 中文教育背景 | `education_background_zh` | 文本型 | - | 学者的中文教育经历信息 | `1989年：加州大学洛杉矶分校（UCLA） 数学博士` |
| 论文数量 | `paper_nums` | 数字型 | 8 | 学者已发表论文的数量 | `492` |
| 被引数量 | `citation_nums` | 数字型 | 8 | 学者论文被引用的总次数 | `35800` |
| H指数 | `h_index` | 数字型 | 8 | 衡量学者学术影响力的 H 指数 | `89` |
| 状态 | `status` | 数字型 | 1 | 0 表示无效，1 表示有效 | `1` |
| 创建时间 | `create_time` | 日期型 | - | 记录创建时间 | `2024/12/17 21:40` |
| 更新时间 | `update_time` | 日期型 | - | 记录最后更新时间 | `2026/5/20 12:00` |

## 2. 学者人才标识 `dwd_scholar_talent_flag`

| 字段中文名称 | 字段英文名称 | 数据类型 | 长度 | 字段描述 | 数据样例 |
|---|---|---:|---:|---|---|
| 学者ID | `scholar_id` | 字符型 | 32 | 关联学者记录的业务唯一标识 | `accc1946` |
| 是否为院士 | `academician` | 字符型 | 128 | 标识学者是否为院士 | `否` |
| 创建时间 | `create_time` | 日期型 | - | 记录创建时间 | `45658.90278` |
| 更新时间 | `update_time` | 日期型 | - | 记录最后更新时间 | `46174.5` |

> 时间样例中的小数是 Excel 日期序列值，导入数据库前必须转换成标准日期时间。

## 3. 学者研究方向 `dwd_scholar_research_direction`

| 字段中文名称 | 字段英文名称 | 数据类型 | 长度 | 字段描述 | 数据样例 |
|---|---|---:|---:|---|---|
| 学者ID | `scholar_id` | 字符型 | 32 | 关联学者记录的业务唯一标识 | `accc1946` |
| 研究方向 | `fields` | 文本型 | - | 学者研究方向 | `应用数学；计算科学；机器学习` |
| 创建时间 | `create_time` | 日期型 | - | 记录创建时间 | `2024/12/17 21:40` |
| 更新时间 | `update_time` | 日期型 | - | 记录最后更新时间 | `2026/5/20 12:00` |

## 4. 学者论文关系 `dwd_scholar_paper_relation`

| 字段中文名称 | 字段英文名称 | 数据类型 | 长度 | 字段描述 | 数据样例 |
|---|---|---:|---:|---|---|
| 论文ID | `paper_id` | 数字型 | 8 | 论文记录的唯一标识 | `1227336496390864901` |
| 论文发表年份 | `year` | 数字型 | 8 | 论文发表年份 | `2026` |
| 学者ID | `scholar_id` | 字符型 | 32 | 学者记录的业务唯一标识 | `accc1946` |
| 被引用次数 | `citations` | 数字型 | 8 | 论文被引用次数 | `32` |
| 发布时间 | `publish_time` | 日期型 | - | 论文发布时间 | `2024/7/21` |
| 状态 | `status` | 数字型 | 1 | 0 表示无效，1 表示有效 | `1` |
| 创建时间 | `create_time` | 日期型 | - | 记录创建时间 | `2024/12/17 21:40` |
| 更新时间 | `update_time` | 日期型 | - | 记录最后更新时间 | `2026/5/20 12:00` |
| 期刊ID | `publication_id` | 数字型 | 8 | 期刊或会议记录的唯一标识 | `100001` |
| 关联论文库ID | `related_paper_id` | 数字型 | - | 关联论文库的唯一标识 | `100001` |

## 5. 论文信息 `dwd_scholar_papers`

| 字段中文名称 | 字段英文名称 | 数据类型 | 长度 | 字段描述 | 数据样例 |
|---|---|---:|---:|---|---|
| 中文题目 | `zh_name` | 字符型 | 500 | 论文的中文标题名称 | `本征铁电体的从头算体自由能面` |
| 英文题目 | `en_name` | 字符型 | 500 | 论文的英文标题名称 | `Ab Initio Bulk Free Energy Surface of Proper Ferroelectrics` |
| 作者列表 | `authors` | 字符型 | 65535 | 论文作者的姓名或信息列表 | `Pinchen Xie；Yixiao Chen；Weinan E；Roberto Car` |
| 论文原始链接 | `paper_url` | 字符型 | 1024 | 论文原始来源页面的访问链接 | `https://doi.org/10.1103/bpz5-2pyw` |
| 发表时间 | `cover_date_start` | 日期型 | - | 论文正式发表或出版的时间 | `2024/7/21` |
| 创建时间 | `create_time` | 日期型 | - | 记录创建时间 | `2024/12/17 21:40` |
| 更新时间 | `update_time` | 日期型 | - | 记录最后更新时间 | `2026/5/20 12:00` |
| 状态 | `status` | 数字型 | 1 | 0 表示无效，1 表示有效 | `1` |
| 中文摘要 | `zh_abstract` | 字符型 | 65535 | 论文内容的中文摘要信息 | `我们报告了一种系统且准确的方法，用于推导体自由能表面。` |
| 英文摘要 | `en_abstract` | 字符型 | 65535 | 论文内容的英文摘要信息 | `We report a systematic and accurate approach for deriving the bulk free energy surface.` |
| DOI | `doi` | 字符型 | 512 | 论文的 DOI 唯一识别号 | `10.1103/bpz5-2pyw` |
| 期刊/会议英文名 | `publication_en_name` | 字符型 | 1024 | 论文发表所在期刊或会议的英文名称 | `Physical Review Letters` |

> 第三方规范没有为该表提供 `paper_id`，因此目前无法仅靠此表字段与 `dwd_scholar_paper_relation.paper_id` 建立可靠外键。

## 6. 学者合作者关系 `dwd_scholar_coauthor`

| 字段中文名称 | 字段英文名称 | 数据类型 | 长度 | 字段描述 | 数据样例 |
|---|---|---:|---:|---|---|
| 学者ID | `scholar_id` | 字符型 | 32 | 当前学者记录的业务唯一标识 | `accc1946` |
| 合作学者ID | `co_scholar_id` | 字符型 | 32 | 合作学者记录的业务唯一标识 | `43a4d7fe` |
| 合作学者英文名 | `co_scholar_name_en` | 字符型 | 256 | 合作学者的英文姓名 | `Linfeng Zhang` |
| 合作学者中文名 | `co_scholar_name_zh` | 字符型 | 128 | 合作学者的中文姓名 | `张林峰` |
| 合作学者头像URL | `co_scholar_avatar` | 字符型 | 512 | 合作学者头像图片的访问链接 | `https://cdn1.deepmd.net/static/img/fbdcfe23d7fef46d_20241204153124.png` |
| 合作学者所属机构英文名 | `co_scholar_org_name_en` | 字符型 | 2048 | 合作学者所属机构的英文名称 | `DP Technology; AI for Science Institute` |
| 合作学者所属机构中文名 | `co_scholar_org_name_zh` | 字符型 | 1024 | 合作学者所属机构的中文名称 | `北京大数据研究院` |
| 合作论文数量 | `co_paper_count` | 数字型 | 8 | 与该学者合作发表的论文数量 | `50` |
| 状态 | `status` | 数字型 | 1 | 0 表示无效，1 表示有效 | `1` |
| 创建时间 | `create_time` | 日期型 | - | 记录创建时间 | `2024/12/17 21:40` |
| 更新时间 | `update_time` | 日期型 | - | 记录最后更新时间 | `2026/5/20 12:00` |

