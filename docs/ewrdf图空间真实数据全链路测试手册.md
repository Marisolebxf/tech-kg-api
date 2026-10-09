# ewrdf 图空间真实数据全链路验证手册(物料级)

> 2026-10-10 v5。目标:在公网门户 `https://edu.itic-sci.com/bkg_zpt` 的部署栈上,用独立 `ewrdf` 图空间跑通**真实数据**全链路,使 **schema 管理、图谱构建、人工审核、平台总览、图谱查询**五个页面全部出现可核验的真实数据。
> v5 变更:**种子数据扩容**(消歧组/失败组/同名高管组/坏论文组成批补齐,人工审核队列从 3 案扩到 **82 案、5 页**);任务测试从 2 条链扩为**三类全覆盖**——**10 个单脚本任务(串行触发)、1 条 6-schema 链、1 个 cron 周期任务(含增量拾取演示)**;「昨日新增」按**北京自然日窗口**(每天北京 00:00 翻日,2026-10-10 口径),全真实数据零造数,并附**授权时间平移**快速验证法(§8.4)。全部预期值均为 2026-10-09/10 实测值(凭证见附录 D/E)。
> v4 变更(保留):删除方案 A,专用测试库 `ewrdf_test` 为唯一路径;全链路 2026-10-09 实测跑通。
> 本手册自带全部物料:10 个 schema 定义、10 个可直接粘贴的抽取脚本、建库脚本(实测库快照 dump,真实 id 全部填好)、三类任务的建法、五页面验证矩阵。
> 所有源数据均为 `gkx_element` 库 `dwd_*` 数仓真实业务数据(真实工商机构/持股/高管、真实论文/作者/期刊),无 mock、无演示造数。

---

## 0. 前提(已实测确认,勿重复排查)

| 事实 | 结论 |
|---|---|
| 公网 `/bkg_zpt` 承载栈 | **dev2 栈**(web 8089/8091、api 8002、worker `tech-kg-temporal-worker-dev2`);8088"主栈"队列无 poller,下发必挂,**勿用** |
| ewrdf 空间 | 已存在(2026-09-19 平台正式创建),0 tag/0 edge,vid=FIXED_STRING(64) |
| 账号 | `642903148@qq.com`(user 241)已授权 ewrdf,登录即可切换 |
| 执行链 | 图谱库 trsgraph 共享、控制库 techkg_control@temporal-mysql-dev2、业务库 gkx_element@tech-kg-mysql(30306)、S3 operator-rustfs 共享、m3e embedding 可用 |
| 抽取空间解析优先级 | **job graphSpace > schema 绑定空间 > worker 默认 dev2** —— 触发时必须显式带 `graphSpace:"ewrdf"` |

**数据量预算(资源红线内,= 2026-10-09/10 实测结果)**:测试库 7 表共 **256 行**(v4 的 101 行基础簇 + v5 扩容的消歧/失败/同名素材组 + 链素材 + 周期素材);图内 **132 实体 + 129 边**(机构 19/高管 46/专家 43/论文 20/期刊 4);人工审核队列 **82 案**(T_LINK 51 + T_EXTRACT_FAIL 28 OPEN,另有 3 RESOLVED,前端 20/页 **5 页**)。任务覆盖三类:**单脚本 ×10(必须串行触发)、chain 链 ×1(6 schema)、cron 周期 ×1**。单 schema 抽取本身秒级分钟级,但**每个实体任务收尾会做整空间索引重建**,与共享 worker 上其他空间的重建互斥(见 §6.1 串行红线);若逢共享图过载波可能拉长到几十分钟,属环境现象非故障。

---

## 1. 总体验证矩阵(做完后逐页核对)

| # | 页面 | 验证点 | 预期 |
|---|---|---|---|
| 1 | Schema 管理 | 目录列表(空间=ewrdf) | 10 个 schema:5 实体 + 5 关系,中文标签正确 |
| 2 | 图谱构建 | 任务列表 + 执行详情 | **三类任务**:10 个单脚本(串行触发;多数 COMPLETED,含行级失败的为 ABNORMAL,素材失败预期内)+ 1 条 6-schema 链(实体→关系顺序)+ 1 个 cron 周期任务(`*/10` 空转→增量拾取→改每日);每 schema 一个抽屉,转换步有真实行数 |
| 3 | 人工审核 | 队列(空间=ewrdf) | **82 真实案、5 页**(20/页):T_LINK 消歧灰区 51 + T_EXTRACT_FAIL 行级失败 28(空名行/坏 id 行/坏论文行)+ 3 RESOLVED;裁决/重跑闭环同 v4 |
| 4 | 平台总览 | 资产卡/昨日新增/审核卡/任务卡 | 实体 **132**、关系 **129**;「昨日新增」为**闭合日窗口 + 北京自然日翻日**(每天北京 00:00 翻):当天跑当天显示 `--`,**次日凌晨 00:00(北京)后**可见当天写入明细(见 §8.4 观察指南);实测 实体 **+42**/关系 **+54** 且明细逐对象实名;审核卡 top5=ewrdf 案;任务卡 12 条 |
| 5 | 图谱查询 | 图控制台 nGQL + 实体检索 | 按 tag 查到点;两跳查询(高管→机构→股东、论文→作者→合著)出真实路径;实体检索能搜到"樊杰"/机构名 |

---

## 2. 数据设计(5 实体 + 5 关系,两个真实数据簇)

### 簇 A:机构域(真实工商数据)

- **6 个闭合持股对**(股东机构与被持股机构都在机构表内,保证 SHAREHOLDER_OF 两端都是实体):
  迈岭信息←富视康(100%)、中科绿谷←深圳先进技术研究院(16.67%)、计量质检院集团←计量质检研究院、平安壹账通云←深圳电商安全证书管理、三本软件←腾云物联(98%)、玖合鑫通讯←玖合鑫科技(100%)
- 机构簇 = 6 被持股方 + 6 持股方 = **12 家**;高管取 6 家被持股方的真实任职行。

### 簇 B:学者域(真实论文数据)

- **10 篇真实中文论文**(经济地理/药学/电力系统类期刊),每篇取前 2 作者 = **20 位真实作者**;
- **消歧组:樊杰 ×3**(170795a9 / 2c3dfa15 / da151)——同一姓名、3 个不同 author_id、institution 全 NULL(真实重名数据)。**实测落图行为**:第 1 行直接落图;后 2 行与已落图同名实体比较,1 行评分越过合并线直接并入(不成案、不新增顶点),另 1 行评分 0.80 落灰区 [0.65,0.85) 扣留成 T_LINK 案——**同名行数 ≠ 案件数**,最终图内只有 1 个樊杰顶点、审核队列 1 案;
- **失败组:空名作者 ×2**——真实数据质量缺陷行(zh_name 为空),进 T_EXTRACT_FAIL;
- 期刊 4 个:经济地理(1009219)、1006062、1004427、1004798(期刊名在 `dwd_zh_journal`,论文表该列全空,别用错表)。

### v5 扩容素材(批量制造"有内容的"失败与消歧案)

在 v4 两簇之上成批补入四组**真实行**(全部 `INSERT IGNORE` + `update_time=NOW()`,选行 SQL 见附录 A):

| 组 | 内容 | 用途 |
|---|---|---|
| 同名专家组 ×36 | 24 行 institution 为 NULL 的真实重名作者 + 12 行「测试比对机构(异地同名)」| 与已落图专家同名比较:灰区扣留成 **T_LINK 案**;NULL 无可比属性 → 评分 0.80 灰区;**专家消歧是"扣留不写图"**(同名行不落顶点) |
| 失败专家组 ×18 | 10 行 institution NULL(空机构触发缺字段)+ 8 行 zh_name 空串 | 行级失败进 **T_EXTRACT_FAIL**;执行终态 ABNORMAL(图已写入的行不受影响) |
| 重复题论文 ×12 + 坏论文 ×8 | 12 行与已落图论文**同题不同 id** + 8 行 bad000pp..bad007pp(NULL/空题名) | 论文同名消歧:同题行扣留成 T_LINK(**不写图**);坏行进 T_EXTRACT_FAIL |
| 同名高管组 ×8 | 8 个**真实高管姓名**挂到新机构(position=「测试同名高管」) | 高管消歧与专家不同:**扣留成 T_LINK 案的同时顶点照写**(vid=org_id__姓名,机构不同即不同 vid)——两种实体类型的消歧口径差异现场 |

另有两组增量素材(测链与周期任务的真实增量):**链素材**(2 篇新论文 + 4 署名行 + ~4 位新专家 + 1 家新机构 + 其真实高管)留给 chain 任务吃;**周期素材**(2 位全新专家,update_time 在建 cron 任务之后才 bump)留给周期任务在下一跳 fire 时增量拾取——见 §6.3。

### Schema 清单

| schema(kind) | 中文名 | 源表 | identity/vid | name 来源 | 关键属性 |
|---|---|---|---|---|---|
| Organization(entity) | 机构 | dwd_org_base_info | org_id | name_cn | province/city/industry/regStatus |
| Officer(entity) | 高管 | dwd_org_executive_info | org_id__姓名 | executives_name | position |
| Expert(entity) | 专家 | dwd_zh_author | author_id | zh_name | institution |
| Paper(entity) | 论文 | dwd_zh_paper | id | zh_name | doi/pubYear |
| Journal(entity) | 期刊 | dwd_zh_journal | publication_id | zh_name | issn |
| EXECUTIVE_OF(relation) | 高管任职 | dwd_org_executive_info | Officer→Organization | — | position |
| SHAREHOLDER_OF(relation) | 股东持股 | dwd_org_shareholder_info | Organization→Organization | — | percentage/ownerName |
| AUTHORED_BY(relation) | 论文署名 | dwd_zh_author | Paper→Expert | — | sequence |
| PUBLISHED_IN(relation) | 发表于 | dwd_zh_paper | Paper→Journal | — | — |
| COAUTHOR_WITH(relation) | 合著 | dwd_zh_author | Expert↔Expert | — | paperId |

> 实体 schema 属性表**必须含 `name`(string)**:建 TAG 时自动建原生索引 `idx_{tag}_name` 并 REBUILD——这是消歧同名召回与实体检索按名查找的命脉。关系 schema 只建 EDGE 无索引,属正常。

---

## 3. 第一步:建 10 个 schema(全局空间切到 ewrdf)

在 Schema 管理页逐个创建(实体建"实体 schema"、关系建"关系 schema",关系需选源/目标实体 schema)。属性定义如下(name 列均为 string、required 建议勾选 name):

**Organization 机构**:name(必需)、province、city、industry、regStatus、capital
**Officer 高管**:name(必需)、position
**Expert 专家**:name(必需)、institution
**Paper 论文**:name(必需)、doi、pubYear
**Journal 期刊**:name(必需)、issn

**EXECUTIVE_OF 任职**:源=Officer,目标=Organization;属性 position
**SHAREHOLDER_OF 股东持股**:源=Organization,目标=Organization;属性 percentage、ownerName
**AUTHORED_BY 论文署名**:源=Paper,目标=Expert;属性 sequence
**PUBLISHED_IN 发表于**:源=Paper,目标=Journal(无业务属性)
**COAUTHOR_WITH 合著**:源=Expert,目标=Expert;属性 paperId

> **无业务属性的关系 schema(如 PUBLISHED_IN)直接保存即可**:平台会自动注入必填审计属性(实体:id/name/create_time/update_time/source_table;关系:create_time/update_time/source_table),UI 新建表单已预置这些行,不必手工添加;走 API 创建时请求体里要带上这三行必填属性(`properties` 至少 1 项的校验也靠它们满足)。

> 建完 schema 立即建源绑定并上传脚本(见下),再触发任务——三件套齐全的 schema 才能抽取。

---

## 4. 第二步:源绑定(专用测试库 ewrdf_test,唯一路径)

> v4 起删除了 v2/v3 的「方案 A:原库 gkx_element + API 覆盖 querySql」路径——UI 表单本身填不了 querySql,必须逐 schema 打浏览器 console 覆盖,且 Journal 绑定实际要翻 2000 行。测试库路径五下拉全自动选对、零 API 覆盖、脚本零改动,实测全链路打通,不再需要备选。

在同一个 MySQL 实例(30306)上新建库 `ewrdf_test`,把白名单行搬进去,再按**普通表**绑定。为什么可行且更省事:

- **数据源不用新建、配置管理零改动**:dev2-default 的账号是 root,库下拉 = 实例级 `SHOW DATABASES`(`backend/service/mysql_datasource.py:list_databases`),新库自动出现在下拉里,数据源仍选 **dev2-default(host.docker.internal,id `MYSQL-430EAF90`)**——下拉里同名杂源很多,认准这个;
- **五个下拉全自动选对**:每张表把真实唯一主键放在第一列(前端 pk 自动偏好 = 有 `id` 列选 `id`,否则选第一列),时间列统一命名 `update_time`(前端时间列自动偏好只认 update_time/updated_at/modified_at/gmt_modified)——选中表后主键列/时间列自动带出,核对一眼即可保存;
- **普通表绑定的 LIMIT/OFFSET 全表翻页在这里无害**:最大的表也只有 27 行;
- **抽取脚本零改动**:测试表列名与脚本读取字段完全同名(row_id 等合成列已物化为真实列);Journal 表已预去重到 4 行,脚本内按 publication_id 去重的逻辑变空转但完全兼容;
- **普通表绑定同样有水位(v5 实测修正 v4 表述)**:绑定行在 `gkx_element.kg_script_watermark` 逐 binding 记 `update_time` 水位,每次执行只读 `update_time > 水位` 的增量行,全部批次成功后推进水位。重跑不会重复读旧行;想重喂某行,把该行 `update_time` bump 到水位之后即可(本手册 §6.1/§6.3 的失败案例复测、周期增量拾取都靠这个语义)。

### 4.0 建库搬数(一次性,只写新库,不动 gkx_element)

> ✅ **2026-10-09 已执行,库已建好并核对;v5 扩容素材已于 2026-10-09/10 补齐**(254 行基线 + 周期素材 2 行)——本节命令只在需要重建时才用。

物料文件:**`docs/ewrdf_test_seed.sql`**(与本手册同分支)。**v5 起种子 = 实测库 `ewrdf_test` 的 mysqldump 快照**:基础簇(§2 簇 A/B)+ v5 扩容素材(同名/失败/链素材)全部物化在 dump 里,重放即得与实测完全一致的库,不依赖 `gkx_element` 的当时状态。**周期素材(wave-3 的 2 位专家)不在种子文件里**——按设计要在建好 cron 任务**之后**才插入(§6.3 时序):重放种子、建好 cron 后,从 `gkx_element.dwd_zh_author` 原样拷贝这两行进 `ewrdf_test.t_expert`(`author_id=c9632ffa55b557b04d01df813472059d` 冯俊新、`15c704db084383208f85c740a39358d8` 王艳),`update_time=NOW()`。宿主机执行:

```bash
cd <仓库检出目录>
docker exec -i tech-kg-mysql mysql --default-character-set=utf8mb4 -uroot -pgkx_element < docs/ewrdf_test_seed.sql
```

⚠ `--default-character-set=utf8mb4` 不能省:实测缺省字符集下中文比较命中 0 行、中文字面量输出全变 `??`。

建好后核对行数(种子脚本头注释里有同款一行命令),预期(= 实测快照):

| 表 | 绑定给 | 行数 | 构成 |
|---|---|---|---|
| t_org | Organization | 19 | 12 基础 + 6 wave-1 + 1 链素材 |
| t_executive | Officer、EXECUTIVE_OF | 46 | 23 基础(4 组双职位合并) + 12 wave-1 + 8 同名高管 + 3 链素材 |
| t_expert | Expert | 99 | 25 基础(含樊杰组/空名 2 行) + 70 wave-1(16 真 + 36 同名 + 18 失败) + 4 链素材(周期素材 2 行建 cron 后再插,见上) |
| t_paper | Paper、PUBLISHED_IN | 40 | 10 基础 + 28 wave-1(8 真 + 12 重复题 + 8 坏行) + 2 链素材 |
| t_journal | Journal | 4 | 按 publication_id 预去重 |
| t_author_paper | AUTHORED_BY、COAUTHOR_WITH | 40 | 20 基础 + 16 wave-1 + 4 链素材 |
| t_shareholder | SHAREHOLDER_OF | 6 | 6 闭合持股对 |

种子共 **254 行**(实测库 256 = 254 + wave-3 周期素材 2 行)。真实内容抽查:机构为真实工商主体(深圳市迈岭信息技术有限公司等);期刊为《经济地理》《电网技术》《电力系统保护与控制》《中国科学院院刊》;专家含樊杰同名组(消歧灰区素材)与空名行(抽取失败素材)。

**真实数据发现(高管同人双职位)**:白名单 6 机构里有 4 人身兼两职(黄小龙 经理/董事、隆晓菁 总经理/董事长、林伟 经理/董事长、尹忠民 总经理/执行董事)。种子脚本按 `(org_id, executives_name)` GROUP BY 合并为一人一行、职位 `GROUP_CONCAT` 保双职(如「经理,董事」)。若不加约束直接搬原表,这 4 人是两行进链路、Officer 实体同 vid 覆盖写,position 只留最后一行的值(信息丢失)——物化 row_id 做主键把真实双职位保住了。这也是物化 row_id 的额外收益:源数据的复合键不唯一在建表时就会暴露(1062 主键冲突),而不是悄悄混进图里。

### 4.1 UI 五下拉选值(选完表后主键列/时间列自动带出,核对即可)

| 绑定给 | 数据源 | 库 | 表 | 主键列(自动) | 时间列(自动) |
|---|---|---|---|---|---|
| Organization | dev2-default | **ewrdf_test** | t_org | org_id | update_time |
| Officer、EXECUTIVE_OF | dev2-default | **ewrdf_test** | t_executive | row_id | update_time |
| Expert | dev2-default | **ewrdf_test** | t_expert | author_id | update_time |
| Paper、PUBLISHED_IN | dev2-default | **ewrdf_test** | t_paper | id | update_time |
| Journal | dev2-default | **ewrdf_test** | t_journal | row_id | update_time |
| AUTHORED_BY、COAUTHOR_WITH | dev2-default | **ewrdf_test** | t_author_paper | row_id | update_time |
| SHAREHOLDER_OF | dev2-default | **ewrdf_test** | t_shareholder | row_id | update_time |

7 张表覆盖 10 个 schema(共用表的各自绑一次,如 Officer 与 EXECUTIVE_OF 都绑 t_executive)。保存后**直接进入第 5 节上传脚本**(脚本零改动)。

### 4.2 测后清理(可选)

```sql
DROP DATABASE IF EXISTS ewrdf_test;
```

注意:清理前确认不再触发抽取(schema 源绑定仍指向该库,库没了再触发会读失败)。新库建在共享实例上同事可见,命名 ewrdf_test 已表明归属;控制库里的 schema 定义/绑定/任务记录不受 DROP 影响,想彻底清场再按平台页面删除 schema/任务即可。

---

## 5. 第三步:上传抽取脚本(10 个,直接粘贴)

脚本契约:`from kg_sdk import step` + `@step def extract(payload)`,吃 `payload["rows"]`,输出实体 `{"entities":[{"id":vid,"props":{...}}],"failures":[{"recordId","error"}]}` / 边 `{"edges":[{"fromId","toId","props":{...}}],"failures":[...]}`。逐行异常进 failures(毒行隔离),不抛出。函数名不得叫 transform/workflow。

> 上传 = 语法检查 + **LLM 安全校验**两道关卡。LLM 环节偶发「LLM 返回格式异常」(实测 10 个脚本遇 2 次),**直接重试一次即可**,不是脚本问题。

### 5.1 Organization
```python
"""Organization(机构)抽取:dwd_org_base_info 行 → 机构实体。"""
from kg_sdk import step


@step
def extract(payload):
    entities, failures = [], []
    for row in payload.get("rows") or []:
        try:
            name = (row.get("name_cn") or "").strip()
            if not name:
                raise ValueError("缺少必需名称字段 name_cn")
            entities.append({
                "id": str(row["org_id"]),
                "props": {
                    "name": name,
                    "province": row.get("province") or "",
                    "city": row.get("city") or "",
                    "industry": row.get("industry_l1_name") or "",
                    "regStatus": row.get("reg_status") or "",
                    "capital": str(row.get("registered_capital_value") or ""),
                },
            })
        except Exception as exc:
            failures.append({"recordId": str(row.get("org_id") or ""), "error": f"{type(exc).__name__}: {exc}"[:1000]})
    return {"entities": entities, "failures": failures}
```

### 5.2 Officer
```python
"""Officer(高管)抽取:dwd_org_executive_info 行 → 高管实体(vid=org_id__姓名)。"""
from kg_sdk import step


@step
def extract(payload):
    entities, failures, seen = [], [], set()
    for row in payload.get("rows") or []:
        try:
            name = (row.get("executives_name") or "").strip()
            if not name:
                raise ValueError("缺少必需名称字段 executives_name")
            vid = f"{row['org_id']}__{name}"
            if vid in seen:  # 同一人在同一机构多行(多职位),合并为一个实体
                continue
            seen.add(vid)
            entities.append({
                "id": vid,
                "props": {"name": name, "position": row.get("executives_position") or ""},
            })
        except Exception as exc:
            failures.append({"recordId": str(row.get("row_id") or ""), "error": f"{type(exc).__name__}: {exc}"[:1000]})
    return {"entities": entities, "failures": failures}
```

### 5.3 Expert
```python
"""Expert(专家)抽取:dwd_zh_author 行 → 专家实体。空名行进 failures(真实数据质量缺陷→T_EXTRACT_FAIL)。"""
from kg_sdk import step


@step
def extract(payload):
    entities, failures, seen = [], [], set()
    for row in payload.get("rows") or []:
        rid = str(row.get("author_id") or "")
        try:
            name = (row.get("zh_name") or "").strip()
            if not name:
                raise ValueError("缺少必需名称字段 zh_name(源行数据质量缺陷)")
            if rid in seen:  # 同一作者多行(多篇论文),合并
                continue
            seen.add(rid)
            entities.append({
                "id": rid,
                "props": {"name": name, "institution": row.get("institution") or ""},
            })
        except Exception as exc:
            failures.append({"recordId": rid, "error": f"{type(exc).__name__}: {exc}"[:1000]})
    return {"entities": entities, "failures": failures}
```

### 5.4 Paper
```python
"""Paper(论文)抽取:dwd_zh_paper 行 → 论文实体。"""
from kg_sdk import step


@step
def extract(payload):
    entities, failures = [], []
    for row in payload.get("rows") or []:
        try:
            name = (row.get("zh_name") or "").strip()
            if not name:
                raise ValueError("缺少必需名称字段 zh_name")
            entities.append({
                "id": str(row["id"]),
                "props": {
                    "name": name,
                    "doi": row.get("doi") or "",
                    "pubYear": str(row.get("cover_year_start") or ""),
                },
            })
        except Exception as exc:
            failures.append({"recordId": str(row.get("id") or ""), "error": f"{type(exc).__name__}: {exc}"[:1000]})
    return {"entities": entities, "failures": failures}
```

### 5.5 Journal
```python
"""Journal(期刊)抽取:dwd_zh_journal 行(一论文一行)按 publication_id 去重 → 期刊实体。"""
from kg_sdk import step


@step
def extract(payload):
    entities, failures, seen = [], [], set()
    for row in payload.get("rows") or []:
        try:
            pid = str(row.get("publication_id") or "")
            name = (row.get("zh_name") or "").strip()
            if not name:
                raise ValueError("缺少必需名称字段 zh_name")
            if pid in seen:
                continue
            seen.add(pid)
            entities.append({
                "id": pid,
                "props": {"name": name, "issn": row.get("issn") or ""},
            })
        except Exception as exc:
            failures.append({"recordId": str(row.get("row_id") or ""), "error": f"{type(exc).__name__}: {exc}"[:1000]})
    return {"entities": entities, "failures": failures}
```

### 5.6 EXECUTIVE_OF
```python
"""EXECUTIVE_OF(高管任职)边:Officer→Organization,一人一机构一条(position 取首行)。"""
from kg_sdk import step


@step
def extract(payload):
    edges, failures, seen = [], [], set()
    for row in payload.get("rows") or []:
        try:
            name = (row.get("executives_name") or "").strip()
            if not name:
                raise ValueError("缺少必需名称字段 executives_name")
            officer_vid = f"{row['org_id']}__{name}"
            if officer_vid in seen:
                continue
            seen.add(officer_vid)
            edges.append({
                "fromId": officer_vid,
                "toId": str(row["org_id"]),
                "props": {"position": row.get("executives_position") or ""},
            })
        except Exception as exc:
            failures.append({"recordId": str(row.get("row_id") or ""), "error": f"{type(exc).__name__}: {exc}"[:1000]})
    return {"edges": edges, "failures": failures}
```

### 5.7 SHAREHOLDER_OF
```python
"""SHAREHOLDER_OF(股东持股)边:股东机构→被持股机构(单位股东,两端都是 Organization 实体)。"""
from kg_sdk import step


@step
def extract(payload):
    edges, failures = [], []
    for row in payload.get("rows") or []:
        try:
            if not (row.get("inv_org_id") and row.get("org_id")):
                raise ValueError("缺少端点机构 id")
            edges.append({
                "fromId": str(row["inv_org_id"]),
                "toId": str(row["org_id"]),
                "props": {
                    "percentage": str(row.get("ownership_percentage") or ""),
                    "ownerName": row.get("owners_name") or "",
                },
            })
        except Exception as exc:
            failures.append({"recordId": str(row.get("row_id") or ""), "error": f"{type(exc).__name__}: {exc}"[:1000]})
    return {"edges": edges, "failures": failures}
```

### 5.8 AUTHORED_BY
```python
"""AUTHORED_BY(论文署名)边:Paper→Expert。"""
from kg_sdk import step


@step
def extract(payload):
    edges, failures = [], []
    for row in payload.get("rows") or []:
        try:
            if not (row.get("paper_id") and row.get("author_id")):
                raise ValueError("缺少 paper_id/author_id")
            edges.append({
                "fromId": str(row["paper_id"]),
                "toId": str(row["author_id"]),
                "props": {"sequence": str(row.get("author_sequence") or "")},
            })
        except Exception as exc:
            failures.append({"recordId": str(row.get("row_id") or ""), "error": f"{type(exc).__name__}: {exc}"[:1000]})
    return {"edges": edges, "failures": failures}
```

### 5.9 PUBLISHED_IN
```python
"""PUBLISHED_IN(发表于)边:Paper→Journal。"""
from kg_sdk import step


@step
def extract(payload):
    edges, failures = [], []
    for row in payload.get("rows") or []:
        try:
            if not (row.get("id") and row.get("publication_id")):
                raise ValueError("缺少论文 id/期刊 publication_id")
            edges.append({
                "fromId": str(row["id"]),
                "toId": str(row["publication_id"]),
                "props": {},
            })
        except Exception as exc:
            failures.append({"recordId": str(row.get("id") or ""), "error": f"{type(exc).__name__}: {exc}"[:1000]})
    return {"edges": edges, "failures": failures}
```

### 5.10 COAUTHOR_WITH
```python
"""COAUTHOR_WITH(合著)边:Expert↔Expert,同一论文的前 2 作者两两成对(脚本内派生)。"""
from collections import defaultdict

from kg_sdk import step


@step
def extract(payload):
    edges, failures = [], []
    by_paper = defaultdict(list)
    for row in payload.get("rows") or []:
        if row.get("paper_id") and row.get("author_id"):
            by_paper[str(row["paper_id"])].append(str(row["author_id"]))
    for paper_id, authors in by_paper.items():
        unique = list(dict.fromkeys(authors))
        for i in range(len(unique)):
            for j in range(i + 1, len(unique)):
                a, b = sorted([unique[i], unique[j]])
                edges.append({"fromId": a, "toId": b, "props": {"paperId": paper_id}})
    return {"edges": edges, "failures": failures}
```

---

## 6. 第四步:建三类任务并触发(单脚本 ×10 串行 → 链 ×1 → 周期 ×1)

> **串行红线(v5 实测教训,最重要的一条)**:实体类抽取收尾会做**整空间索引重建**,重建有 worker 进程级全局单飞锁。**同一 worker 上任何空间的重建进行中时**,其他实体任务的索引步会 `EntitySearchReindexInProgressError` 重试 5 次(2s/4s/8s/16s 退避,约 1 分钟耗尽)后**整任务 FAILED**。因此:
> 1. **单脚本任务一个跑完终态再建/触发下一个**(本手册实测 10 个全串行,除撞上别人空间的重建外全部一次通过);
> 2. 触发前如看到别的空间在重建索引(实体检索页/worker 日志),等它结束;
> 3. 失败在索引步的执行,**行已写图但终态 FAILED,不建审核案、不进昨日新增**——重触发前先把想让它读的行 bump 过水位(见 §6.1 末);
> 4. 控制库执行状态是**惰性刷新**:Temporal 已终态、列表仍显示 RUNNING 时,打开一次任务详情即回落。

### 6.1 单脚本任务 ×10(先实体后关系,严格串行)

图谱构建页逐个建「单 Schema 抽取」任务(extract 类型,单 schemaId),`graphSpace` 显式 `ewrdf`,`batchSize=200`(表最大 101 行,一批过);建一个→立即触发→**等终态**→再建下一个。顺序与实测结果(2026-10-09,执行 ID 见附录 D):

| 序 | schema | 终态 | written | 说明 |
|---|---|---|---|---|
| 1 | Journal 期刊 | COMPLETED | 0 | 无新期刊行,空转正常 |
| 2 | Organization 机构 | COMPLETED | 6 | wave-1 六家真实机构 |
| 3 | Officer 高管 | COMPLETED | 20 | 12 真实 + 8 同名高管(**顶点照写** + 同名消歧成 T_LINK 案) |
| 4 | Expert 专家 | **ABNORMAL** | 16 | 16 真实落图;33 同名扣留成 T_LINK(不写图);18 坏行行级失败成 T_EXTRACT_FAIL;ABNORMAL=行级失败聚合,图已写入不受影响 |
| 5 | Paper 论文 | FAILED ×2 → 复测 **ABNORMAL** | 2 + 8 行级失败 | 见下方"索引锁复测"(复测凭证 EXEC-5233F4AF4C8348EB,附录 E) |
| 6-10 | 5 个关系 schema | COMPLETED | 任职 12/股东 0/署名 16/发表于 18/合著 8 | 关系任务不做索引重建,可紧跟着跑,仍建议串行 |

**Paper 索引锁复测(✅ 2026-10-09 已实测)**:5 个实体任务并行触发的实测结果是最先拿到锁的几个靠 activity 重试侥幸通过、Paper 两次 FAILED(重试 5 次耗尽,行已写图但不建案、不计昨日新增)。等锁空闲后重触发:一次性读入 wave-1 剩余的 8 行坏论文(`bad000pp..bad007pp`,失败素材)+ 2 行链素材真实论文 → **EXEC-5233F4AF4C8348EB 终态 ABNORMAL**(written=2 + 行级失败 8 案,新 T_EXTRACT_FAIL 案落袋)。两个实测教训:①**索引步可静默跑十几分钟**——该次索引重建恰逢共享图拥塞尾波,19:42→20:01 共 18 分钟,进度日志每 5000 行才打一条、小空间全程无输出,别误判卡死;②**列表显示 RUNNING 16+ 分钟是惰性刷新**——Temporal 早已终态,打开一次任务详情即回落 ABNORMAL(§6 串行红线第 4 条)。想重喂任意行:`UPDATE ewrdf_test.t_paper SET update_time=NOW() WHERE id IN (...)` 把行顶过水位即可,老行/坏行不会重复读。

API 等价(单脚本):
```bash
curl -X POST http://localhost:8002/api/v1/workflow-system/jobs -H 'Content-Type: application/json' -d \
'{"taskType":"extract","name":"ewrdf-单脚本-机构","schemaId":"<Organization的schemaId>",
  "graphSpace":"ewrdf","batchSize":200,"runNow":true}'
# 已建任务的重触发:
curl -X POST http://localhost:8002/api/v1/workflow-system/jobs/<jobId>/trigger
```
(schemaId 在 schema 管理页每个 schema 的详情里;勿用 /task-center/trigger 全量扫)

### 6.2 链任务 ×1(6 schema:实体→关系一条链)

串行 10 个单脚本全部到终态后,建 chain 任务把 wave-2 链素材(2 论文 + 4 署名 + ~4 专家 + 1 机构 + 3 高管)一口气吃完。schemaIds 顺序 = **实体在前、关系在后**:

```bash
curl -X POST http://localhost:8002/api/v1/workflow-system/jobs -H 'Content-Type: application/json' -d \
'{"taskType":"chain","name":"ewrdf-链串行-全链","graphSpace":"ewrdf","batchSize":200,"runNow":true,
  "schemaIds":["<Organization>","<Officer>","<Expert>","<Paper>","<AUTHORED_BY>","<PUBLISHED_IN>"]}'
```

chain 内部严格串行:同一时刻只有一个 schema 在写图;任一环**执行级**失败整链 FAILED(逐行 failures 不算失败,只进审核,整链终态 ABNORMAL)。链里的实体 schema 步同样各做一次索引重建(三步之间自然互斥,链内无并发问题)。

**✅ 2026-10-09 实测(两次触发,教训+成功各一)**:
- 首触发 EXEC-4945248C2F4F445A:2 分钟即 COMPLETED 但**接近空转**——链素材多数已在单脚本轮被吃或在水位之上(§6.1 的 Paper 复测恰好吃掉了 2 行链素材论文)。**想吃饱必须先把素材 bump 过水位再触发**:`UPDATE ewrdf_test.t_org SET update_time=NOW() WHERE org_id='<链素材机构>';`(t_executive/t_expert/t_paper/t_author_paper 同理,§4.0 的链素材行)。
- bump wave-2/3 后重触发 **EXEC-7209BED4D7B84312:COMPLETED,六环全过零失败**——Org 1 / Officer 3 / Expert 6 / Paper 2 / AUTHORED_BY 4 / PUBLISHED_IN 2,图内净增 **+12 顶点 / +6 边**(UTC 20:0x 写入,属北京 10-10 窗口)。
- 链执行 output 无 sources,**不计入昨日新增**(§8.4 计入口径),链的图增量看图统计。
- ⚠ **空步也推水位**:某环没有新行可读(空转)时,该环绑定水位照样推进到执行开始时刻——实测链的空转 Expert 环把水位推过了 18:57 插入的周期素材,下一跳 cron fire 拾取不到,只能再 bump 一遍(wave-3 复插语义,§6.3)。

### 6.3 周期任务 ×1(cron `*/10` 空转 → 增量拾取 → 改每日)

```bash
# 1) 建周期任务(runNow=false,由 cron 驱动;先选 Expert,源表小、空转快)
curl -X POST http://localhost:8002/api/v1/workflow-system/jobs -H 'Content-Type: application/json' -d \
'{"taskType":"extract","name":"ewrdf-周期-专家","schemaId":"<Expert的schemaId>","graphSpace":"ewrdf",
  "batchSize":200,"runNow":false,"schedule":{"kind":"cron","cron":"*/10 * * * *","timezone":"Asia/Shanghai"}}'
# 2) 观察至少 2 跳空转 fire(每跳 COMPLETED、written=0:水位之后无新行,索引重建照做——这就是增量语义)
# 3) 滴灌增量:bump/插入 2 行新专家(update_time=NOW() > 水位)
#    UPDATE ewrdf_test.t_expert ... / INSERT INTO ewrdf_test.t_expert VALUES (...)
# 4) 等下一跳 fire:该执行 COMPLETED 且 written=2 —— 周期任务增量拾取实证
# 5) 演示完毕改为每日一跑并保持启用(留作常驻周期任务):
curl -X PUT http://localhost:8002/api/v1/workflow-system/jobs/<jobId> -H 'Content-Type: application/json' -d \
'{"schedule":{"kind":"cron","cron":"23 8 * * *","timezone":"Asia/Shanghai"}}'
```

要点:cron 按 `timezone` 对齐墙钟(`*/10` 在每小时的 :00/:10:… 触发);fire 产生的执行 triggerSource=**SCHEDULE**;空转 fire 也走完整链路含索引重建,若 fire 恰逢其他空间重建中,该 fire 会 FAILED——周期任务选在空闲时段演示。

**✅ 2026-10-09 实测(job-ecfa466f38ee,Expert)**:`*/10` 时段多跳 fire 里 **2 跳 FAILED**(恰逢外部空间索引重建,印证上面的时段提醒)→ 拥塞退去后 **EXEC-334BE6BB3C0F4DE1 空转 COMPLETED(written=0)**——水位之后无新行,索引重建照做,增量语义实证;bump wave-3 两行(冯俊新/王艳,`update_time=NOW()`)后下一跳 **EXEC-2D759A26CCA64227 拾取 COMPLETED(written=2)**,两专家落图。⚠ wave-3 首次拾取为空的原因即 §6.2 的"空步推水位"(链的空转 Expert 环先把水位推过了 18:57 的行)——**滴灌素材要 bump 到"最后一次任何执行开始时刻"之后**才算增量。演示完毕已改 **`23 8 * * *` Asia/Shanghai 每日一跑并保持启用**(留作常驻周期任务;每日 fire 的空转/拾取就是现成的周期回归观测点)。

---

## 7. 第五步:人工审核(实测 82 案 / 5 页)

三类任务到终态后,运营中心 → 人工审核队列(空间=ewrdf,默认 20 条/页,可切 10/20/50/100),应出现 **82 案、5 页**(= 2026-10-10 实测;队列落在**业务库** `gkx_element.manual_review_case`,按 `template_id` 区分):

| 案件类型 | 来源 | 实测量 |
|---|---|---|
| 实体对齐裁决(T_LINK)OPEN | 同名专家 33(24 NULL 机构评分 0.80 灰区 + 12 异地同名机构)+ 同名高管 8(新机构真实高管名)+ 樊杰组遗留 1 | **51** |
| 抽取失败重跑(T_EXTRACT_FAIL)OPEN | 专家坏行 18(NULL 机构 10 + 空名 8)+ 论文坏行 8(bad000pp..bad007pp NULL/空题名,Paper 复测落袋)+ 重跑回滚 2(空名行 attempt=2 回 OPEN) | **28** |
| 已裁决(RESOLVED) | v4 期 3 案(樊杰 merge 1 + 空名重跑 2) | 3 |

**同名行数 ≠ 案件数 ≠ 落图数**(实测口径,消歧三向分流):Expert 同名 36 行 → 33 扣留成案 + 3 评分越线自动并入 + **0 落图**;Officer 同名 8 行 → 8 成案且**顶点照写**(vid=org_id__姓名,机构不同即不同 vid)——**专家是"扣留不写",高管是"成案也写",两类实体的消歧口径差是现成的规则验证素材**。重复题论文 12 行实测 10 扣留 + 2 并入(不写图)。

**裁决操作**(页面按钮等价;API 形态如下,直审模式无需先领取,OPEN 状态可直接提交):

- T_LINK 裁决 merge(实测通过):

```bash
POST /api/v1/manual-reviews/production/{caseId}/submit
{"version": 1,                              # 案件详情里的 version,提交成功后 +1
 "actionId": "entity-confirm",              # 动作枚举:entity-confirm | reject-candidate
 "result": {"entityVerdict": "merge",       # 裁决枚举:merge | create | retype(retype 暂不支持)
            "targetEntityId": "170795a90339520c3673f72508b5ba6f"},   # 必须是案内候选集 vid
 "note": "同名灰区 0.80,并入论文作者樊杰"}
```

  merge 效果(实测):扣留记录并入目标顶点(空值列不覆盖已有值),图内仍只有 1 个樊杰、Expert 计数不变(21),da151 顶点不落图;案终态 RESOLVED。`entityVerdict=create` 则按快照里的预留 vid 新建顶点。
- 审计与证据:`GET /api/v1/manual-reviews/production/{id}/audit-logs` 可见 CASE_CREATED 与 DECISION_SUBMITTED(明细含 `applied:true / verdict / vid / pendingRelationsWritten`);
- T_EXTRACT_FAIL:点「重跑」→ `POST /api/v1/manual-reviews/production/rerun-extract-failures` `{"caseIds":["...","..."],"batchSize":10}` → 新执行 triggerSource=**RERUN**。**注意这两行是真实空名行,重跑仍会失败**(数据本身缺陷):实测旧 2 案转 RESOLVED、新 2 案以 attempt=2 回到 OPEN,错误为「缺少必需名称字段 zh_name(源行数据质量缺陷)」——失败回滚 OPEN 属正常,正好验证重跑闭环。

> 裁决写图按 case 建案时烙定的 ewrdf 空间,不受当前空间切换影响;但审完前别切走空间,防误操作。

---

## 8. 第六步:五页面验证

### 8.1 Schema 管理页
空间=ewrdf:10 个 schema(机构/高管/专家/论文/期刊 + 5 关系),中文名、属性、脚本、源绑定齐全。

### 8.2 图谱构建页
三类任务全在列表:10 个单脚本(多数 COMPLETED,Expert ABNORMAL、Paper 复测 ABNORMAL 属行级预期;若曾撞索引锁会有 FAILED 历史)+ 1 条 6-schema 链 + 1 个周期任务(SCHEDULE 触发的多跳执行);点开执行详情,每个 schema 抽屉显示真实转换行数。API 核对:`GET /api/v1/workflow-system/jobs/{id}` 看 `data.job.lastExecutionStatus`,执行详情 `GET /workflow-system/executions/{id}` 看 `data.output.failures`。⚠ 控制库状态**惰性刷新**:Temporal 已终态而列表仍 RUNNING 时,打开详情即回落(见 §6 串行红线第 4 条)。

### 8.3 人工审核页
82 案/5 页(20/页)分页浏览;裁决后队列状态 RESOLVED;重跑后旧案 RESOLVED + 新案 OPEN(attempt=2);审计日志可查 DECISION_SUBMITTED(实测明细:`applied:true, verdict:merge, vid:170795a9…, pendingRelationsWritten:0`)。挑案建议:先做 1 个 T_LINK merge(樊杰组语义与 v4 相同)再重跑 2 个 T_EXTRACT_FAIL(空名行重跑仍失败、回 OPEN attempt=2,验证重跑闭环)。

### 8.4 平台总览页(空间=ewrdf)
- 资产卡:实体 **132**、关系 **129**(2026-10-10 实测;API `GET /api/v1/platform/overview?space=ewrdf` → `assetOverviewGroups`,同时给出昨日新增 `+42`/`+54` 徽标);
- **「昨日新增」观察指南(全真实数据,零造数;北京自然日窗口)**:
  - **窗口**:按**北京自然日**聚合,统计日 = 昨天(北京时间),**每天凌晨 00:00(北京)翻日**(2026-10-10 用户口径,`_DAY_TZ=Asia/Shanghai`,env `PLATFORM_OVERVIEW_DAY_TIMEZONE` 可覆写;此前版本按 api 容器 UTC 日在北京 08:00 翻日,已改)。执行完成时刻(completedAt,UTC 写入)折算北京后归属统计日;明细行时间列(完成时刻与图反查的逐对象写入时间)均按北京时刻展示;
  - **计入口径**:单 schema 执行的 `output.kind ∈ {entity,relation}` 且 `sources[].written` 求和 > 0,终态 COMPLETED 或 **ABNORMAL 都算**(图已写入必须计入);**FAILED 不算**(索引失败=任务失败,写入也不认);**chain 链执行没有 sources,天然不计入**——链的写入要看图统计,不要等它出现在昨日新增;
  - **明细行怎么来的**:计数来自控制库执行 payload;逐对象明细是拿执行的读取窗口 `[startWatermark, completedAt]` 到图里按 `update_time` **时间窗 LOOKUP 反查**(顶点带 `idx_{tag}_ut`、边带 `idx_{edge}_ut` 时间索引,§9 红线表)。查不到窗口内对象时**诚实降级**为「类型 · N 条」聚合行,不编造对象名;
  - **✅ 2026-10-10 前端实测值**:实体 **+42**(机构 6/高管 20/专家 16,明细 42 行全部逐对象实名:盛司潼、隆晓菁、汪滔…,来源列真实源表)、关系 **+54**(任职 12/署名 16/合著 8/发表于 18,明细 38 行:米伟铭 → 叶鹏 等)。两处口径差:**发表于 明细行 2/18**——Paper 复测在批次之后又重写了同键 paper→journal 边,把 16 条边的 `update_time` 刷出了旧执行窗口(upsert 覆盖语义,**计数不受影响、仅明细行少**);属正常行为,不是丢数;
  - **数字对不上时先核对三件事**:完成时刻折算北京后的日期、终态、output.sources.written——任一不满足就不计入,属口径而非丢数;
- **授权时间平移快速验证法(用户 2026-10-10 授权,不改数据内容只改时间戳)**:自然观察要等次日翻日;想当天立刻在前端看到,把计数批次整体平移进"昨天":
  1. **控制库**:7 个计数执行 payload 里 `completedAt/startedAt` 及 sources 的 `startWatermark/watermark` 统一 −8h(`techkg_control.workflow_executions`,先备份 payload 原值);
  2. **图侧**:对应 42 顶点 + 54 边的 `update_time` 同步 −8h——⚠ 顶点正确语法是 **`UPDATE VERTEX ON \`Tag\` "vid" SET ...`**,没有 `UPDATE TAG ON` 这种写法(实测 400 SyntaxError);边是 `UPDATE EDGE ON \`TYPE\` "src"->"dst"@rank SET ...`;
  3. **前置**:时间窗 LOOKUP 依赖手工建的时间索引(`CREATE TAG INDEX idx_{tag}_ut ON {tag}(update_time(20))` + **`REBUILD TAG INDEX`**——REBUILD 是异步 job,提交后 `SHOW JOBS` 确认 FINISHED;忘了 REBUILD 索引只含建后增量,LOOKUP 会漏历史行,实体明细降级聚合);
  4. **清缓存**:结果按 (空间, 日) 进程内缓存到当天结束、每 worker 一份——`docker restart tech-kg-api-dev2` 后首个请求重算即得全量明细(图服务空闲时反查 0.02s/条;共享图过载波时 LOOKUP 可能部分返回/超时,换个时段重启重算即可)。
  平移后 completedAt 折算北京仍落在同一统计日(−8h 后北京 17:58,仍属 10-09),**次日翻日后依然可见**,不用改回;原始值备份在会话机 `$CLAUDE_JOB_DIR/tmp/ewrdf_shift_backup.json`;
- 人工审核卡:top5 显示 ewrdf 自己的案;图谱构建任务卡:12 条。

### 8.5 图谱查询(图控制台,只读,以下 nGQL 全部实测通过)

⚠ **MATCH 里属性必须带 tag 前缀**(`v.Organization.name`),裸 `v.name` 经网关返回空对象不报错,极易误判成"没数据"。

```bash
# 以下经图网关执行(X-API-Key + X-Graph-Space: ewrdf),浏览器图控制台等价
# 1) 按标签查点(实测 12 行,含 province)
MATCH (v:`Organization`) RETURN v.Organization.name AS name, v.Organization.province AS province LIMIT 12
# 2) 两跳模式匹配:高管 → 任职机构 ← 股东(实测 10 行,如 王岳→玖合鑫通讯←玖合鑫科技)
MATCH (o:Officer)-[:EXECUTIVE_OF]->(g:Organization)<-[:SHAREHOLDER_OF]-(s:Organization)
RETURN o.Officer.name AS officer, g.Organization.name AS org, s.Organization.name AS shareholder LIMIT 10
#    GO 等价(⚠ 单个 GO 不能按边混方向,REVERSELY 会作用于全部边;混合方向用 BIDIRECT,实测 4 行)
GO 2 STEPS FROM "e9f6a720f02bb2143dd0f926b82f07f3__王岳" OVER EXECUTIVE_OF, SHAREHOLDER_OF BIDIRECT
YIELD DISTINCT id($$) AS endpoint
# 3) 论文 → 作者 / 期刊(实测 20 行 / 10 行,期刊见《电网技术》《经济地理》)
MATCH (p:Paper)-[:AUTHORED_BY]->(e:Expert) RETURN p.Paper.name AS paper, e.Expert.name AS author LIMIT 20
MATCH (p:Paper)-[:PUBLISHED_IN]->(j:Journal) RETURN p.Paper.name AS paper, j.Journal.name AS journal LIMIT 10
# 4) 同名实体(消歧现场;merge 裁决后实测仅 1 行 vid=170795a9…)
MATCH (v:`Expert`) WHERE v.Expert.name == '樊杰' RETURN id(v) AS vid, v.Expert.institution AS inst
```

- **实体检索页/API**(实测即测即得,不用手动建索引):任一实体任务收尾已自动建好 ewrdf 分区索引——`GET /api/v1/entity-search/index-status?space=ewrdf`(⚠ 参数名是 `space`,不是 `graphSpace`)返回 `indexed:true`;实测命中(⚠ 字段名是 `keyword`):`POST /api/v1/entity-search/search` `{"keyword":"盛司潼","space":"ewrdf"}`(wave-1 高管,Officer 型)、`"汪滔"`(v4 高管)、`"冯俊新"`(wave-3 周期拾取专家)、`"樊杰"`、`"深圳先进技术研究院"` 全部返回真实属性(position/institution 等)。⚠ **typeCounts 只是"最近一次重建的记录口径",不是图内实数**:实测 Officer 记 3/图实 46、Expert 记 6/图实 43——共享图拥塞期的重建会按标签跳过,记录计数偏低但 Milvus 实际内容不受影响(上面各姓名照常命中);空闲时段任一实体任务收尾或 `POST /api/v1/entity-search/reindex` `{"space":"ewrdf"}` 可刷新记录。若恰逢重建进行中(`reindexing:true`),等重建结束再查。

---

## 9. 风险与红线

| 项 | 说明 |
|---|---|
| 串行触发 | **实体任务一个跑完再触发下一个**:索引重建是 worker 进程级全局单飞锁,并发触发实测会把后到的打成 FAILED(§6 串行红线);周期任务避开别的空间的重建时段 |
| 资源红线 | 只绑 `ewrdf_test` 的 7 张小表(实测库共 256 行 = 种子 254 + wave-3 周期素材 2,每表 ≤101 行)。batchSize=200,**勿对 gkx_element 的 dwd_* 大表做全表绑定**;共享图过载波时抽取变慢属正常,勿反复重启 |
| 图侧时间索引 | 平台建 TAG 只自动建 `idx_{tag}_name`(schema_ddl),**没有 update_time 索引**;「昨日新增」逐对象反查、任何按 update_time 的时间窗 LOOKUP 都要先手工 `CREATE TAG/EDGE INDEX idx_*_ut ON x(update_time(20))` + **`REBUILD TAG/EDGE INDEX`**(异步 job,`SHOW JOBS` 确认 FINISHED;只 CREATE 不 REBUILD 索引里只有建后增量,LOOKUP 漏历史行)。改顶点时间用 **`UPDATE VERTEX ON \`Tag\` "vid" SET …`**(`UPDATE TAG ON` 不存在此语法,400),边用 `UPDATE EDGE ON \`TYPE\` "src"->"dst"@rank SET …` |
| 图网关错误体 | trs-graph REST 400/500 响应形如 `{"error","message","status"}`、**没有 summary.errorCode**——脚本判错要同时看 `error` 字段,只查 summary 会把 400 当成功吞掉(v5 实测:顶点时间平移首次全数静默失败即此因) |
| 静默写错空间 | 触发任务必须显式 `graphSpace:"ewrdf"`;不带时最坏写进 worker 默认空间 dev2 |
| 共享环境 | 控制库曾有未知清理者删 schema(2026-09-23);业务库全栈共享——建库搬数只**读** gkx_element 白名单行,写只落在新建 `ewrdf_test` 库;别人的数据(尤其 review_widgets 等)不碰 |
| vid 上限 | ewrdf vid=FIXED_STRING(64):机构/作者 32 位、论文 19 位、Officer 复合 vid ~44 字节,均安全;自增字段别超 64 |
| T_DIRECT | 现行抽取链不产生 T_DIRECT;若在库里看到存量 T_DIRECT 案,勿在 ewrdf 测 accept(非 RBAC 下会写默认空间) |
| 幂等重跑 | **普通表绑定有水位**(v5 修正):每次执行只读 `update_time > 水位` 的增量行,重跑不重复读旧行;想重喂把行 bump 过水位(INSERT VERTEX 覆盖语义幂等);消歧合并过的顶点重跑不会拆开 |

---

## 10. 附录

### A. id 白名单的选簇 SQL(想换一批数据时用)
```sql
-- 机构簇:6 个闭合持股对(两端都在机构表,且被持股方有高管行)
SELECT s.org_id, s.inv_org_id, o1.name_cn, o2.name_cn, s.ownership_percentage
FROM gkx_element.dwd_org_shareholder_info s
JOIN gkx_element.dwd_org_base_info o1 ON o1.org_id = s.org_id
JOIN gkx_element.dwd_org_base_info o2 ON o2.org_id = s.inv_org_id
WHERE s.owners_type = '单位'
  AND EXISTS (SELECT 1 FROM gkx_element.dwd_org_executive_info e WHERE e.org_id = s.org_id)
LIMIT 6;

-- 论文簇:有≥2署名的论文 10 篇(期刊信息要 JOIN dwd_zh_journal 取,论文表 publication_zh_name 全空)
SELECT a.paper_id, p.zh_name FROM
 (SELECT paper_id FROM gkx_element.dwd_zh_author WHERE zh_name<>''
   GROUP BY paper_id HAVING COUNT(DISTINCT author_id)>=2 ORDER BY paper_id LIMIT 10) a
JOIN gkx_element.dwd_zh_paper p ON p.id = a.paper_id;

-- 消歧组:真实重名作者(institution 为 NULL → 评分 0.80 进灰区)
SELECT zh_name, COUNT(DISTINCT author_id) ids FROM gkx_element.dwd_zh_author
WHERE institution IS NULL AND zh_name<>'' GROUP BY zh_name HAVING ids>=3 ORDER BY ids DESC LIMIT 5;

-- 失败组:真实空名行
SELECT author_id, paper_id FROM gkx_element.dwd_zh_author WHERE zh_name IS NULL OR zh_name='' LIMIT 2;
```

### B. 真实性凭证(2026-10-09 实测)
- dwd_org_base_info 1,674 行(真实工商机构)、dwd_org_executive_info 5,600 行、dwd_org_shareholder_info 含真实持股比例;
- dwd_zh_paper 2,000 行、dwd_zh_author 7,906 行(真实论文/作者/机构署名);
- 樊杰 14 个不同 author_id(institution 全 NULL)、空名作者 6 行——均为库中真实存在的数据。

### C. 机制依据(代码相对路径)
- 脚本契约:`backend/script/extract_transform_common.py`(entities/edges/failures 项格式、毒行隔离);
- @step 唯一入口、chain 任务类型、querySql 水位/pk keyset、T_EXTRACT_FAIL 逐行建案:`CLAUDE.md` 平台喂数批次抽取节;
- 抽取空间解析(job graphSpace > schema 行 > env 默认):`backend/service/temporal_workflows.py` `_extract_schema`;
- 实体 TAG 自动 name 索引 `idx_{tag}_name`:`backend/service/schema_ddl.py`;
- 实体检索单集合 kg_entity 按空间分区、新空间首检需建索引:`backend/service/entity_search.py`;
- 消歧同名召回(Nebula MATCH 非 Milvus):`backend/service/entity_disambiguation.py`;
- 审核 case 空间烙定 + 队列 graphSpace 过滤:`backend/service/manual_review_production.py`;
- 索引重建单飞锁(进程级 `_reindex_running` + MySQL 咨询锁)与索引失败即 FAILED 口径:`backend/service/entity_search.py:reindex`、`backend/service/temporal_workflows.py`(build_entity_index,ACTIVITY_RETRY_POLICY 5 次);
- 控制库执行状态惰性刷新(列表/详情/触发时向 Temporal 复核):`backend/service/workflow_jobs.py:_refresh_running_jobs`;
- 「昨日新增」聚合口径(**北京自然日统计日** `_DAY_TZ`/`_completed_in_day_tz`、kind∈{entity,relation}、sources.written>0、ABNORMAL 计入、逐对象图反查窗口 `[startWatermark, completedAt]`、(空间,日) 进程内缓存):`backend/service/platform_overview.py`;
- 普通表绑定水位(kg_script_watermark 按 binding 记 update_time):`backend/service/temporal_workflows.py` 抽取读where + 批次成功推进(**空读也推进**)。

### D. 2026-10-09 全链路实测凭证(v4 修订依据)

按本手册 v4 从头到尾执行一遍,全部环节打通,关键凭证:

| 环节 | 结果 |
|---|---|
| Schema(§3) | 10 个 schema 建齐(复用空间内已有 Organization),实体 4 新建 + 关系 5 新建 |
| 源绑定(§4) | 10 个绑定全部指向 ewrdf_test 7 表(dev2-default),五下拉自动选对 |
| 脚本(§5) | 10 个脚本上传过 LLM 安全校验(2 次「LLM 返回格式异常」重试即过) |
| 任务(§6) | job-4734842e96ef(实体链)EXEC-42EAB2F489CB4232 终态 **ABNORMAL**(failures 2/recorded 2);job-89278755c92a(关系链)EXEC-B83AACCEF8CB41C1 终态 **COMPLETED** 零失败:任职 23/股东持股 6/论文署名 20/发表于 10/合著 10 |
| 审核(§7) | 队列 3 案;T_LINK MR-20261009-4830E3C83D26 提交 merge(0.80 灰区)→ RESOLVED,audit-logs 见 DECISION_SUBMITTED applied:true;T_EXTRACT_FAIL 2 案 rerun → EXEC-C212D766875145C9(triggerSource=RERUN)仍失败,旧案 RESOLVED、新案 MR-20261009-8451652F0BDD / MR-20261009-AC28B94C2A2B OPEN(attempt=2) |
| 图内容 | 顶点 70(机构 12/高管 23/专家 21/论文 10/期刊 4)、边 69;merge 后图内仅 1 个樊杰(vid 170795a9…),da151 不落图 |
| 总览(§8.4) | `GET /platform/overview?space=ewrdf` 29ms:assetOverviewGroups 实体 70/关系 69,分段与图一致;昨日新增当日 `--`(闭合日窗口,次日可见) |
| 实体检索(§8.5) | index-status(space=ewrdf)indexed:true,typeCounts 五类齐;搜"樊杰"/"深圳先进技术研究院"各 1 命中 |

### E. 2026-10-09/10 v5 扩容实测凭证(单脚本/链/周期三类)

种子扩容(wave-1/2/3)后按 §6 三类任务全串行实测,控制库执行凭证(UTC 时间):

**单脚本 10 个(§6.1,2026-10-09 17:4x-18:0x)**:

| schema | job | 执行 | 终态 | written |
|---|---|---|---|---|
| Journal | job-848c2a93e2f3 | EXEC-C1E2B86396814F76 | COMPLETED | 0 |
| Organization | job-db6544dd4f43 | EXEC-C3738D38B551463F | COMPLETED | 6 |
| Officer | job-439a571993ce | EXEC-1259F69B6AD9461F | COMPLETED | 20 |
| Expert | job-f53bf5e1d9bf | EXEC-213E77F9EA5A4FF6 | **ABNORMAL** | 16(33 同名扣留 T_LINK + 18 坏行 T_EXTRACT_FAIL) |
| Paper | job-b9ae08feabd1 | EXEC-E983FA93EF0D457E / EXEC-06C9455C49414BEE | **FAILED ×2** | 0(两次均撞外部 dev2 空间索引重建,重试 5 次耗尽;第一次抽取行已写图 Paper=18,但不建案不计昨日新增) |
| EXECUTIVE_OF | job-ddc46537ebac | EXEC-C729000995AC4BA4 | COMPLETED | 12 |
| SHAREHOLDER_OF | job-d357c4d7f67a | EXEC-0804C5EFA1BA4784 | COMPLETED | 0 |
| AUTHORED_BY | job-383f0f5f8d7b | EXEC-702EB4E238F54D1C | COMPLETED | 16 |
| PUBLISHED_IN | job-1bfa03dff7cc | EXEC-6D31BE0834234FF5 | COMPLETED | 18 |
| COAUTHOR_WITH | job-77c76bfd6086 | EXEC-158529C781824BB1 | COMPLETED | 8 |

**Paper 索引锁复测(§6.1)**:等锁空闲后重触发 **EXEC-5233F4AF4C8348EB 终态 ABNORMAL**(completedAt 2026-10-09 20:01:02 UTC)——written=2(2 行链素材真实论文)+ 行级失败 8(bad000pp..bad007pp,8 个新 T_EXTRACT_FAIL 案落袋)。附带实测:该次索引重建恰逢共享图拥塞尾波,**19:42→20:01 共 18 分钟静默执行**(进度日志每 5000 行一条,小空间全程无输出);期间控制库列表显示 RUNNING 16+ 分钟,属惰性刷新,打开任务详情即回落 ABNORMAL。

**链任务(§6.2,job 对应 chain 类型)**:
| 触发 | 执行 | 终态 | 结果 |
|---|---|---|---|
| 首触发(素材未 bump) | EXEC-4945248C2F4F445A | COMPLETED | 2 分钟空跑——链素材已在单脚本轮被吃/水位之上(教训:**先 bump 素材再触发链**) |
| bump wave-2/3 后重触发 | **EXEC-7209BED4D7B84312** | **COMPLETED** | 六环全过零失败:Org 1 / Officer 3 / Expert 6 / Paper 2 / AUTHORED_BY 4 / PUBLISHED_IN 2;图净增 **+12 顶点 / +6 边**(UTC 20:03-20:2x 写入,属北京 10-10 窗口;链执行无 sources,不计昨日新增) |

**周期任务(§6.3,job-ecfa466f38ee,Expert)**:`*/10 * * * *` Asia/Shanghai 时段多跳 fire——**2 跳 FAILED**(18:0x,恰逢外部空间索引重建,重试耗尽;印证"周期任务避开重建时段")→ 拥塞退去后 **EXEC-334BE6BB3C0F4DE1 空转 COMPLETED(written=0**,索引重建照做,增量语义实证)→ bump wave-3 两行(冯俊新 `c9632ffa55b557b04d01df813472059d` / 王艳 `15c704db084383208f85c740a39358d8`)后 **EXEC-2D759A26CCA64227 拾取 COMPLETED(written=2)**,两专家 20:20 落图。首跳拾取为空是链空转 Expert 环先推过水位(§6.2 空步推水位)。演示后已改 **`23 8 * * *` 每日一跑,保持启用**。

**人工审核队列(§7,2026-10-10 实测,业务库 gkx_element.manual_review_case)**:
| template_id | OPEN | RESOLVED | 合计 |
|---|---|---|---|
| T_LINK 实体对齐 | 51 | 1 | 52 |
| T_EXTRACT_FAIL 抽取失败 | 28 | 2 | 30 |
| **合计** | **79** | **3** | **82(20/页 × 5 页)** |

**平台总览「昨日新增」(§8.4,2026-10-10 前端实测)**:资产卡 实体 132(+42)/ 关系 129(+54);明细行 **实体 42 行全部逐对象实名**(机构 6/高管 20/专家 16;盛司潼、隆晓菁、汪滔…;来源列 ewrdf_test.t_executive 等真实源表;时间列北京时刻如 10-09 17:51:07)、**关系 38 行**(任职 12/署名 16/合著 8/发表于 2;米伟铭 → 叶鹏 等)。发表于明细 2/18:Paper 复测重写同键边把 16 条 update_time 刷出旧窗口(upsert 覆盖,计数不变仅明细少)。为当天即验,按 §8.4 授权时间平移法把 7 个计数执行(上表 10 个单脚本中 written>0 且终态 COMPLETED/ABNORMAL 的 7 个:Org/Officer/Expert/EXECUTIVE_OF/AUTHORED_BY/PUBLISHED_IN/COAUTHOR_WITH;Journal 与 SHAREHOLDER_OF 空转不计,Paper 两次 FAILED 及其 20:01 复测均不计——复测属北京 10-10 窗,次日才可见)的 payload 时刻与对应 42 顶点/54 边图侧 update_time 整体 −8h,重启 api 清 (空间,日) 快照后全量实名可见;4 次调用结果一致。

**图终态(§8.5,2026-10-10 实测,LOOKUP 逐 tag/edge 计数)**:顶点 **132** = 机构 19 + 高管 46 + 专家 43 + 论文 20 + 期刊 4(高管 46 = v4 23 + wave-1 20 + 链 3;专家 43 = 21 + 16 + 6;机构 19 = 12 + 6 + 1);边 **129** = EXECUTIVE_OF 35 + SHAREHOLDER_OF 6 + AUTHORED_BY 40 + PUBLISHED_IN 30 + COAUTHOR_WITH 18。实体检索 `index-status?space=ewrdf`:`indexed:true / reindexing:false`,实测命中 盛司潼(wave-1)/汪滔(v4)/冯俊新(wave-3)/樊杰/深圳先进技术研究院;typeCounts 记录口径偏低(Officer 3/Expert 6,拥塞期按标签跳过所致),搜索不受影响,详见 §8.5。⚠ 共享图服务偶发过载波会**部分返回**(本节计数过程中 Organization LOOKUP 一次返回 0,重试即恢复 19)——图侧点验数字对不上时先重试再看结论。
