# gkx\_kg实体属性与关系映射

## 1\. 实体与属性

### Event（事件）　表：`kg_event`

|属性名|数据表名|数据字段名|属性意思|
|---|---|---|---|
|（vid）|kg\_event|event\_id|主键，取自点 id 剥类型前缀|
|event\_type|kg\_event|event\_type|表级常量（annual\_finance/financing/bid/bankruptcy/shixin/zhixing/judicial\_case 等）|
|raw\_id|kg\_event|raw\_id|同 event\_id 口径|
|title|kg\_event|title|候选链 title/project\_name/case\_title/job\_title/funding\_round/…；全空→表中文名|
|content|kg\_event|content|候选链 content/penalty\_content/violation\_fact/legal\_obligation/exec\_target/…；全空→整行 JSON|
|case\_no|kg\_event|case\_no||
|case\_cause|kg\_event|case\_cause|候选链 case\_cause/case\_type/case\_type\_tag|
|occur\_date|kg\_event|occur\_date|候选链 publish\_time/public\_date/penalty\_date/procedure\_date/filing\_date/occur\_period/year；M8 筛选|
|amount|kg\_event|amount|候选链 amount/funding\_amount/fine\_amount/exec\_target/project\_budget\_amount/total\_assets；M8 影响力分/M9 徽标|
|currency|kg\_event|currency|候选链 currency/currency\_code/funding\_currency\_code/amount\_unit|
|organization\_id|kg\_event|organization\_id||
|source\_system|kg\_event|source\_system||
|source\_table|kg\_event|source\_table|16 张事件源表名（分表映射见设计文档 3\.6）|
|source\_record\_id|kg\_event|source\_record\_id||
|source\_url|kg\_event|source\_url||
|ingest\_batch|kg\_event|ingest\_batch||
|ingest\_time|kg\_event|ingest\_time||
|source\_update\_time|kg\_event|source\_update\_time||
|extra\_json 及未落列属性|kg\_event|extra\_json|兜底：图上多余属性与此列合并的 JSON|

### IndustryChain（产业链）　表：`kg_industry_chain`

|属性名|数据表名|数据字段名|属性意思|
|---|---|---|---|
|（vid）|kg\_industry\_chain|chain\_code|主键，取自点 id 剥类型前缀|
|chain\_name|kg\_industry\_chain|chain\_name|M8 产业链行/M9 摘要|
|source\_table|kg\_industry\_chain|source\_table||
|ingest\_batch|kg\_industry\_chain|ingest\_batch||
|ingest\_time|kg\_industry\_chain|ingest\_time||
|extra\_json 及未落列属性|kg\_industry\_chain|extra\_json|兜底：图上多余属性与此列合并的 JSON|

### IndustryNode（产业链节点）　表：`kg_industry_node`

|属性名|数据表名|数据字段名|属性意思|
|---|---|---|---|
|（vid）|kg\_industry\_node|node\_id|主键，取自点 id 剥类型前缀|
|node\_name|kg\_industry\_node|node\_name|M8 链节点/M9 核心技术层 label|
|node\_type|kg\_industry\_node|node\_type|2=叶子环节（企业多挂叶）；M9 副标题候选|
|level|kg\_industry\_node|level||
|node\_seq|kg\_industry\_node|node\_seq||
|node\_imp\_level|kg\_industry\_node|node\_imp\_level||
|node\_stage|kg\_industry\_node|node\_stage||
|node\_path|kg\_industry\_node|node\_path||
|source\_table|kg\_industry\_node|source\_table||
|ingest\_batch|kg\_industry\_node|ingest\_batch||
|ingest\_time|kg\_industry\_node|ingest\_time||
|extra\_json 及未落列属性|kg\_industry\_node|extra\_json|兜底：图上多余属性与此列合并的 JSON|

### Journal（期刊）　表：`kg_journal`

|属性名|数据表名|数据字段名|属性意思|
|---|---|---|---|
|（vid）|kg\_journal|publication\_id|主键，取自点 id 剥类型前缀|
|name\_zh|kg\_journal|name\_zh|← zh\_name|
|name\_en|kg\_journal|name\_en|← en\_name|
|name\_abbr|kg\_journal|name\_abbr|← name\_abbr（两表同列）|
|issn\_print|kg\_journal|issn|← zh\.issn / en\.issn\_print|
|issn\_online|kg\_journal|eissn|← zh\.eissn / en\.issn\_online|
|country|kg\_journal|country||
|establish\_time|kg\_journal|founding\_time|← zh\.founding\_time / en\.establish\_time|
|impact\_factor|kg\_journal|impact\_factor||
|is\_sci|kg\_journal|is\_sci|M6 期刊分级|
|jcr\_zone|kg\_journal|jcr\_zone|仅英文刊表；M6 期刊分级|
|scope\_zone|kg\_journal|scope\_zone|仅英文刊表（中科院分区）；M6 期刊分级|
|sub\_quartile|kg\_journal|sub\_quartile|仅中文刊表；M6 期刊分级|
|top|kg\_journal|top|仅英文刊表；M6 期刊分级|
|zh\_core|kg\_journal|zh\_core|← zh\.classify\_list（北大核心/CSCD 等）；M6 期刊分级|
|cite\_nums|kg\_journal|cite\_nums|仅中文刊表|
|annual\_publication|kg\_journal|annual\_publication||
|publish\_period|kg\_journal|publication\_cycle|← zh\.publication\_cycle / en\.publish\_period|
|source|kg\_journal|source|常量 zh\_journal/en\_journal|
|source\_system|kg\_journal|source\_system||
|source\_table|kg\_journal|source\_table||
|source\_record\_id|kg\_journal|source\_record\_id||
|ingest\_batch|kg\_journal|ingest\_batch||
|ingest\_time|kg\_journal|ingest\_time||
|source\_update\_time|kg\_journal|source\_update\_time||
|extra\_json 及未落列属性|kg\_journal|extra\_json|兜底：图上多余属性与此列合并的 JSON|

### Keyword（关键词）　表：`kg_keyword`

|属性名|数据表名|数据字段名|属性意思|
|---|---|---|---|
|（vid）|kg\_keyword|keyword\_id|主键，取自点 id 剥类型前缀|
|keyword|kg\_keyword|keyword|改text:图上240点为65k字符词表串|
|source\_system|kg\_keyword|source\_system||
|citation\_nums|kg\_keyword|citation\_nums||
|source\_table|kg\_keyword|source\_table||
|source\_record\_id|kg\_keyword|source\_record\_id||
|source\_url|kg\_keyword|source\_url||
|ingest\_batch|kg\_keyword|ingest\_batch||
|ingest\_time|kg\_keyword|ingest\_time||
|source\_update\_time|kg\_keyword|source\_update\_time||
|organization\_base|kg\_keyword|organization\_base||
|organization\_id|kg\_keyword|organization\_id||
|extra\_json 及未落列属性|kg\_keyword|extra\_json|兜底：图上多余属性与此列合并的 JSON|

### News（新闻）　表：`kg_news`

|属性名|数据表名|数据字段名|属性意思|
|---|---|---|---|
|（vid）|kg\_news|news\_id|主键，取自点 id 剥类型前缀|
|title|kg\_news|title|← news\_title（链上 or title 兜底）|
|content|kg\_news|content|← news\_content / summary（链上）|
|release\_date|kg\_news|release\_date|← news\_date / relaese\_date（源表列名原样拼写）|
|original\_url|kg\_news|original\_url|← original\_textlink；链上来源恒空|
|organization\_id|kg\_news|organization\_id||
|source\_system|kg\_news|source\_system||
|source\_table|kg\_news|source\_table|dwd\_org\_important\_news\_info / dwd\_industry\_chain\_news\_info|
|source\_record\_id|kg\_news|source\_record\_id||
|source\_url|kg\_news|source\_url||
|ingest\_batch|kg\_news|ingest\_batch||
|ingest\_time|kg\_news|ingest\_time||
|source\_update\_time|kg\_news|source\_update\_time||
|extra\_json 及未落列属性|kg\_news|extra\_json|兜底：图上多余属性与此列合并的 JSON|

### Organization（机构/企业）　表：`kg_organization`

|属性名|数据表名|数据字段名|属性意思|
|---|---|---|---|
|（vid）|kg\_organization|org\_id|主键，取自点 id 剥类型前缀|
|name\_cn|kg\_organization|name\_cn|候选链 name\_cn/org\_loc\_name/company\_name/n\_company\_name/traditional\_name/name\_alias/name\_en|
|name\_en|kg\_organization|name\_en|← name\_en/en\_name|
|source|kg\_organization|source||
|external\_id|kg\_organization|external\_id|← external\_id/company\_code/school\_code/credit\_no；链上回填=credit\_code|
|province|kg\_organization|province||
|city|kg\_organization|city||
|area|kg\_organization|area||
|country\_code|kg\_organization|country\_code||
|country|kg\_organization|country||
|address|kg\_organization|address|← address/company\_address/reg\_address|
|postal\_code|kg\_organization|postal\_code||
|phone|kg\_organization|phone||
|email|kg\_organization|email||
|legal\_rep|kg\_organization|legal\_rep|← lerep/legal\_person/legal\_name|
|org\_type|kg\_organization|org\_type|← org\_type/univ\_type/company\_type/industry\_type|
|org\_size|kg\_organization|org\_size|← person\_num/employees\_number|
|founded\_year|kg\_organization|founded\_year|← incorporation\_year/est\_year/incorporation\_date|
|listing\_status|kg\_organization|listing\_status|← listing\_status/listed\_status（stock\_base）；M7 行业地位/经营状况|
|listed\_date|kg\_organization|listed\_date|← stock\_base\.listed\_date|
|registered\_capital|kg\_organization|registered\_capital|← registered\_capital\_value/capital\_num/capital；M7 经营状况|
|capital\_currency|kg\_organization|capital\_currency|← capital\_currency/currency\_code/currency|
|industry\_class|kg\_organization|industry\_class|← industry/industry\_class/industry\_l1\_name；M7 合作领域/M9 副标题|
|stock\_code|kg\_organization|stock\_code|← stock\_base\.stock\_code|
|stock\_noun|kg\_organization|stock\_noun|← stock\_base\.stock\_noun|
|stock\_type|kg\_organization|stock\_type|← stock\_base\.stock\_type；M7 行业地位|
|org\_kind|kg\_organization|org\_kind|来源表常量（domestic\_organization/domestic\_university/…/industry\_chain\_enterprise）|
|description|kg\_organization|description|← description/main\_activities/business\_scope；M7|
|main\_products|kg\_organization|main\_products|← main\_products/main\_prod（产品经营表）/tech\_product聚合（链上回填）；M7|
|organization\_base|kg\_organization|organization\_base||
|organization\_id|kg\_organization|organization\_id||
|manual\_disabled|kg\_organization|manual\_disabled|修正中心运行时列|
|correction\_id|kg\_organization|correction\_id|修正中心运行时列|
|corrected\_at|kg\_organization|corrected\_at|修正中心运行时列|
|source\_system|kg\_organization|source\_system||
|source\_table|kg\_organization|source\_table||
|source\_record\_id|kg\_organization|source\_record\_id||
|source\_url|kg\_organization|source\_url||
|ingest\_batch|kg\_organization|ingest\_batch||
|ingest\_time|kg\_organization|ingest\_time||
|source\_update\_time|kg\_organization|source\_update\_time||
|extra\_json 及未落列属性|kg\_organization|extra\_json|兜底：图上多余属性与此列合并的 JSON|

### Paper（论文）　表：`kg_paper`

|属性名|数据表名|数据字段名|属性意思|
|---|---|---|---|
|（vid）|kg\_paper|id|主键，取自点 id 剥类型前缀|
|title\_zh|kg\_paper|title\_zh|← zh\_name|
|title\_en|kg\_paper|title\_en|← en\_name|
|doi|kg\_paper|doi||
|publication\_year|kg\_paper|publication\_year|← cover\_year\_start（M3 完成时间/M6 时间过滤）|
|publication\_date|kg\_paper|publication\_date|← cover\_date\_start|
|language|kg\_paper|language|← zh\.language\_classify / en\.language|
|document\_type|kg\_paper|document\_type|← paper\_type|
|publication\_type|kg\_paper|publication\_type||
|publication\_id|kg\_paper|publication\_id|← dwd\_zh/en\_paper\.publication\_id；PUBLISHED\_IN 关系的实体侧外键（=kg\_journal 主键）|
|volume|kg\_paper|volume||
|issue|kg\_paper|issue||
|first\_page|kg\_paper|start\_page|← first\_page|
|last\_page|kg\_paper|end\_page|← last\_page|
|is\_oa|kg\_paper|is\_oa|← open\_access|
|paper\_url|kg\_paper|source\_url|← paper\_url|
|source|kg\_paper|source|← data\_source（缺省 zh\_paper/en\_paper）|
|created\_time|kg\_paper|created\_time||
|updated\_time|kg\_paper|updated\_time||
|output\_awards|kg\_paper|output\_awards|← dwd\_scholar\_papers\.operator\_remarks（严格 JSON 门禁）|
|source\_system|kg\_paper|source\_system||
|source\_table|kg\_paper|source\_table||
|source\_record\_id|kg\_paper|source\_record\_id||
|ingest\_batch|kg\_paper|ingest\_batch||
|ingest\_time|kg\_paper|ingest\_time||
|source\_update\_time|kg\_paper|source\_update\_time||
|match\_method|kg\_paper|match\_method||
|match\_evidence|kg\_paper|match\_evidence||
|organization\_base|kg\_paper|organization\_base||
|organization\_id|kg\_paper|organization\_id||
|extra\_json 及未落列属性|kg\_paper|extra\_json|兜底：图上多余属性与此列合并的 JSON|

### Patent（专利）　表：`kg_patent`

|属性名|数据表名|数据字段名|属性意思|
|---|---|---|---|
|（vid）|kg\_patent|patent\_id|主键，取自点 id 剥类型前缀|
|publication\_number|kg\_patent|publication\_number||
|application\_number|kg\_patent|application\_number|← application\_reference JSON $\.apno|
|application\_kind|kg\_patent|application\_kind||
|country\_code|kg\_patent|country\_code||
|country|kg\_patent|country||
|publication\_date|kg\_patent|publication\_date|← publication\_reference JSON $\.pbdt|
|application\_date|kg\_patent|application\_date|← application\_reference JSON $\.apdt；M7 合作时间|
|granted\_number|kg\_patent|granted\_number||
|grant\_date|kg\_patent|grant\_date|← dwd\_patent\_legal\.dates\_of\_public\_availability $\.date|
|status|kg\_patent|status|← dwd\_patent\_legal\.status|
|anticipated\_expiration|kg\_patent|anticipated\_expiration|← dwd\_patent\_legal\.anticipated\_expiration|
|title\_original|kg\_patent|title\_original|← dwd\_patent\_title\.titles（JSON text/content 换行连接）|
|title\_en|kg\_patent|title\_en|← dwd\_patent\_title\.title\_localized|
|title\_zh|kg\_patent|title\_zh|← dwd\_patent\_title\.title\_zh|
|abstract\_zh|kg\_patent|abstract\_zh|← dwd\_patent\_abstract\.abstract\_zh|
|language|kg\_patent|language|← dwd\_patent\.language（JSON 数组逗号join）|
|main\_ipcr|kg\_patent|main\_ipcr|← main\_classification\_ipcr|
|further\_ipcr|kg\_patent|further\_ipcr|← further\_classification\_ipcr（JSON 快照）|
|main\_cpc|kg\_patent|main\_cpc|← main\_classification\_cpc|
|further\_cpc|kg\_patent|further\_cpc|← further\_classification\_cpc（JSON 快照）|
|keywords|kg\_patent|keywords|← dwd\_patent\.keywords（JSON 快照；M3 所属领域）|
|citation\_nums|kg\_patent|citation\_nums|← dwd\_patent\_cited\.reference\_cited|
|cited\_by\_nums|kg\_patent|cited\_by\_nums|← dwd\_patent\_cited\.cited\_by\_nums|
|patent\_value|kg\_patent|patent\_value|← dwd\_patent\.value|
|simple\_family\_number|kg\_patent|simple\_family\_number|← dwd\_patent\_family\.simple\_family\_number|
|db\_source|kg\_patent|db\_source||
|create\_time|kg\_patent|create\_time||
|update\_time|kg\_patent|update\_time||
|title|kg\_patent|title|展示回退链列（演示批/回填）|
|source|kg\_patent|source||
|output\_awards|kg\_patent|output\_awards||
|evaluation|kg\_patent|evaluation||
|source\_system|kg\_patent|source\_system||
|source\_table|kg\_patent|source\_table||
|source\_record\_id|kg\_patent|source\_record\_id||
|source\_url|kg\_patent|source\_url||
|ingest\_batch|kg\_patent|ingest\_batch||
|ingest\_time|kg\_patent|ingest\_time||
|source\_update\_time|kg\_patent|source\_update\_time||
|match\_method|kg\_patent|match\_method||
|match\_evidence|kg\_patent|match\_evidence||
|organization\_base|kg\_patent|organization\_base||
|organization\_id|kg\_patent|organization\_id||
|extra\_json 及未落列属性|kg\_patent|extra\_json|兜底：图上多余属性与此列合并的 JSON|

### PatentFamily（专利同族）　表：`kg_patent_family`

|属性名|数据表名|数据字段名|属性意思|
|---|---|---|---|
|（vid）|kg\_patent\_family|family\_number|主键，取自点 id 剥类型前缀|
|organization\_base|kg\_patent\_family|organization\_base||
|organization\_id|kg\_patent\_family|organization\_id||
|source\_table|kg\_patent\_family|source\_table||
|source\_record\_id|kg\_patent\_family|source\_record\_id||
|ingest\_batch|kg\_patent\_family|ingest\_batch||
|ingest\_time|kg\_patent\_family|ingest\_time||
|extra\_json 及未落列属性|kg\_patent\_family|extra\_json|兜底：图上多余属性与此列合并的 JSON|

### Person（专家/人物）　表：`kg_person`

|属性名|数据表名|数据字段名|属性意思|
|---|---|---|---|
|（vid）|kg\_person|person\_id|主键，取自点 id 剥类型前缀|
|name\_en|kg\_person|name\_en|← dwd\_scholar\.name\_en / dwd\_zh\_author\.en\_name|
|name\_zh|kg\_person|name\_zh|← dwd\_scholar\.name\_zh / dwd\_zh\_author\.zh\_name|
|name\_cn|kg\_person|name\_cn|← 任职批 executives\_name/bo\_name/entity\_name/owners\_name；法人批 lerep/legal\_person|
|email|kg\_person|email|学者批恒空串|
|source|kg\_person|source|常量 scholar（学者批）|
|person\_kind|kg\_person|person\_kind|shareholder/executive/beneficial\_owner/actual\_controller/legal\_representative|
|country\_code|kg\_person|country\_code|放宽:图上34字符旧测试批脏值|
|country|kg\_person|country|← dm\_nationalities/country|
|birth\_date|kg\_person|birth\_date|← dm\_birthdate/bo\_birthdate/birth\_date|
|gender|kg\_person|gender|放宽:同上|
|biography|kg\_person|biography|← dwd\_scholar\.bio / dm\_biography|
|bio\_zh|kg\_person|bio\_zh|← dwd\_scholar\.bio\_zh|
|avatar|kg\_person|avatar|← dwd\_scholar\.avatar|
|scholar\_org|kg\_person|scholar\_org|← dwd\_scholar\.scholar\_org\_name\_zh OR scholar\_org\_name\_en（摘要单位行/画布副标题）|
|paper\_nums|kg\_person|paper\_nums|← dwd\_scholar\.paper\_nums（M9 指标徽标）|
|citation\_nums|kg\_person|citation\_nums|← dwd\_scholar\.citation\_nums（M9 指标徽标）|
|h\_index|kg\_person|h\_index|← dwd\_scholar\.h\_index（M9 指标徽标）|
|scholar\_status|kg\_person|scholar\_status|← dwd\_scholar\.status|
|is\_academician|kg\_person|is\_academician|← dwd\_scholar\_talent\_flag\.academician（最新一条）|
|research\_fields|kg\_person|research\_fields|← dwd\_scholar\_research\_direction\.fields（分号拼接；M6 主题兜底）|
|work\_experience\_date|kg\_person|work\_experience\_date|← dwd\_scholar\.work\_experience\_date（M4 时段/M7 合作时间）|
|work\_experience\_institution\_en|kg\_person|work\_experience\_institution\_en||
|work\_experience\_department\_en|kg\_person|work\_experience\_department\_en||
|work\_experience\_position\_en|kg\_person|work\_experience\_position\_en||
|work\_experience\_institution\_zh|kg\_person|work\_experience\_institution\_zh||
|work\_experience\_department\_zh|kg\_person|work\_experience\_department\_zh|M4 部门判定|
|work\_experience\_position\_zh|kg\_person|work\_experience\_position\_zh|M4 头衔/M7·M8 角色|
|education\_background\_date|kg\_person|education\_background\_date|M5 同期判定|
|education\_background\_institution\_en|kg\_person|education\_background\_institution\_en|M5 同校判定（LOOKUP 兜底键）|
|education\_background\_degree\_en|kg\_person|education\_background\_degree\_en|M5 同学历判定|
|education\_background\_institution\_zh|kg\_person|education\_background\_institution\_zh|M5 同校判定（LOOKUP 兜底键）|
|education\_background\_degree\_zh|kg\_person|education\_background\_degree\_zh|M5 同学历判定|
|source\_system|kg\_person|source\_system||
|source\_table|kg\_person|source\_table||
|source\_record\_id|kg\_person|source\_record\_id||
|source\_url|kg\_person|source\_url||
|ingest\_batch|kg\_person|ingest\_batch||
|ingest\_time|kg\_person|ingest\_time||
|source\_update\_time|kg\_person|source\_update\_time||
|match\_method|kg\_person|match\_method||
|match\_evidence|kg\_person|match\_evidence||
|organization\_base|kg\_person|organization\_base||
|organization\_id|kg\_person|organization\_id||
|extra\_json 及未落列属性|kg\_person|extra\_json|兜底：图上多余属性与此列合并的 JSON|

### Product（产品）　表：`kg_product`

|属性名|数据表名|数据字段名|属性意思|
|---|---|---|---|
|（vid）|kg\_product|product\_id|主键，取自点 id 剥类型前缀|
|name|kg\_product|name|改text:图上1518字符产品串|
|category|kg\_product|category|← target\_item\_type/industry\_class|
|description|kg\_product|description|← description/main\_activities|
|organization\_id|kg\_product|organization\_id||
|source\_system|kg\_product|source\_system||
|source\_table|kg\_product|source\_table||
|source\_record\_id|kg\_product|source\_record\_id||
|source\_url|kg\_product|source\_url||
|ingest\_batch|kg\_product|ingest\_batch||
|ingest\_time|kg\_product|ingest\_time||
|source\_update\_time|kg\_product|source\_update\_time||
|extra\_json 及未落列属性|kg\_product|extra\_json|兜底：图上多余属性与此列合并的 JSON|

### Project（项目）　表：`kg_project`

|属性名|数据表名|数据字段名|属性意思|
|---|---|---|---|
|（vid）|kg\_project|id<br>|主键，取自点 id 剥类型前缀|
|project\_number|kg\_project|project\_number||
|title|kg\_project|title||
|project\_source|kg\_project|project\_source||
|project\_level|kg\_project|project\_level||
|project\_host|kg\_project|project\_host||
|funded\_amount|kg\_project|funded\_amount||
|discipline|kg\_project|discipline||
|discipline\_code|kg\_project|discipline\_code||
|fund\_category|kg\_project|fund\_category||
|funded\_province|kg\_project|funded\_region||
|approval\_year|kg\_project|approval\_year|date→ISO 文本；M7 合作时间|
|approval\_time|kg\_project|approval\_time||
|research\_period|kg\_project|research\_period||
|abstract|kg\_project|abstract||
|final\_report\_abstract|kg\_project|final\_report\_abstract|仅中文项目表有；英文表恒空|
|project\_page\_url|kg\_project|project\_page\_url||
|source|kg\_project|source|常量 zh\_project/en\_project|
|total\_outputs|kg\_project|total\_outputs|以下 11 计数列 ← dwd\_\*\_project\_output 同名列|
|journal\_articles\_count|kg\_project|journal\_articles\_count||
|conference\_papers\_count|kg\_project|conference\_papers\_count||
|books\_count|kg\_project|books\_count||
|degree\_papers\_count|kg\_project|degree\_papers\_count||
|patents\_count|kg\_project|patents\_count||
|clinical\_trials\_count|kg\_project|clinical\_trials\_count|中文表恒 0|
|products\_count|kg\_project|products\_count|恒 0（SQL 常量）|
|awards\_count|kg\_project|awards\_count||
|reports\_count|kg\_project|reports\_count||
|other\_outputs\_count|kg\_project|other\_outputs\_count||
|output\_awards|kg\_project|output\_awards|← output\_awards JSON 规范化串；M3 奖项|
|keywords|kg\_project|keywords|← keywords JSON 快照|
|evaluation|kg\_project|evaluation|← operator\_remarks 严格门禁|
|source\_system|kg\_project|source\_system||
|source\_table|kg\_project|source\_table||
|source\_record\_id|kg\_project|source\_record\_id||
|source\_url|kg\_project|source\_url||
|ingest\_batch|kg\_project|ingest\_batch||
|ingest\_time|kg\_project|ingest\_time||
|source\_update\_time|kg\_project|source\_update\_time||
|match\_method|kg\_project|match\_method||
|match\_evidence|kg\_project|match\_evidence||
|extra\_json 及未落列属性|kg\_project|extra\_json|兜底：图上多余属性与此列合并的 JSON|

### Report（研究报告）　表：kg\_report

|属性名|数据表名|数据字段名|属性意思|
|---|---|---|---|
|（主键）<br>|kg\_report|report\_id|主键=两源表 report\_id；zh=UUID\(36位\)、en=KJBG\+13位数字，无交集|
|title\_cn|kg\_report|title\_cn|中文报告题名（←zh）|
|abstract\_cn|kg\_report|abstract\_cn|中文摘要（←zh）|
|keywords\_cn|kg\_report|keywords\_cn|中文关键词，JSON 数组（←zh）|
|report\_type|kg\_report|report\_type|报告类型：最终报告等（←zh）|
|report\_category|kg\_report|report\_category|报告分类：医药、卫生等（←zh）|
|approval\_year|kg\_report|approval\_year|批准/立项年份（←zh，2,000/2,000 有值）|
|preparation\_time|kg\_report|preparation\_time|编写时间，8 位日期串（←zh）|
|project\_annual\_number|kg\_report|project\_annual\_number|项目年度编号（←zh）|
|contact\_phone|kg\_report|contact\_phone|联系电话（←zh）|
|source\_org|kg\_report|source\_org|来源机构，JSON 数组如 \["广州医科大学"\]（←zh）|
|related\_institutions|kg\_report|related\_institutions|相关机构（←zh）|
|related\_paper\_id|kg\_report|related\_paper\_id|相关论文 id（←zh）|
|related\_project\_id|kg\_report|related\_project\_id|相关项目 id（←zh）|
|related\_projects|kg\_report|related\_projects|相关项目名称（←zh）|
|visibility\_scope|kg\_report|visibility\_scope|可见范围（←zh）|
|title\_en|kg\_report|title\_en|英文报告题名（←en）|
|abstract\_en|kg\_report|abstract\_en|英文摘要（←en）|
|keywords\_en|kg\_report|keywords\_en|英文关键词，JSON 数组（←en）|
|category|kg\_report|category|报告分类（←en 侧）|
|document\_type|kg\_report|document\_type|文档类型（←en）|
|report\_number|kg\_report|report\_number|报告编号（←en）|
|contract\_number|kg\_report|contract\_number|合同号（←en）|
|corporate\_author|kg\_report|corporate\_author|机构作者，JSON（←en）|
|author\_id|kg\_report|author\_id|作者 id，JSON（←en）|
|country|kg\_report|country|国家（←en）|
|pub\_year|kg\_report|pub\_year|出版年份（←en；源表恒空，列保留）|
|publication\_date|kg\_report|publication\_date|出版日期，8 位串（←en，1,000/1,000 有值；=图 Report\.publication\_date 来源）|
|source\_agency|kg\_report|source\_agency|来源机构（←en 侧）|
|related\_literature\_id|kg\_report|related\_literature\_id|相关文献 id，JSON（←en）|
|authors|kg\_report|authors|作者列表，JSON（共有；2,971/3,000 有值）|
|organization|kg\_report|organization|所属机构（共有；zh 为 JSON 数组、en 为纯文本，取宽 mediumtext，zh 行存 JSON 串）|
|content|kg\_report|content|报告正文（共有；源表恒空，列保留）|
|page\_count|kg\_report|page\_count|页数（共有；=图 Report\.page\_count 来源）|
|related\_author\_id|kg\_report|related\_author\_id|相关作者 id，JSON（共有）|
|related\_authors|kg\_report|related\_authors|相关作者名称，JSON（共有）|
|related\_literature|kg\_report|related\_literature|相关文献，JSON（共有）|
|related\_org\_id|kg\_report|related\_org\_id|相关机构 id，JSON（共有；源表恒空，列保留）|
|file\_path|kg\_report|file\_path|文件路径（共有；类型取宽 varchar\(500\)）|
|file\_type|kg\_report|file\_type|文件类型（共有；类型取宽 varchar\(100\)）|
|source\_url|kg\_report|source\_url|来源链接（共有；类型取宽 text，两源表全有值）|
|dwd\_id|kg\_report|dwd\_id|数仓代理键 bigint（共有）|
|table\_data\_source|kg\_report|table\_data\_source|数据来源标记（共有；源表恒 NULL）|
|is\_deleted|kg\_report|is\_deleted|删除标记（共有；恒 0）|
|insert\_remark|kg\_report|insert\_remark|插入备注（共有）|
|operator\_remarks|kg\_report|operator\_remarks|操作备注（共有）|
|creater|kg\_report|creater|创建人（共有）|
|updater|kg\_report|updater|更新人（共有）|
|created\_time|kg\_report|created\_time|创建时间 datetime（共有）|
|updated\_time|kg\_report|updated\_time|更新时间 datetime（共有）|

## 2\. 关系



|关系|名称|起点实体 → 终点实体|连接键（gkx\_kg 表\.id）|说明（间接分析得到的）|
|---|---|---|---|---|
|HAS\_NEWS|机构关联新闻|Organization → News|kg\_organization\.org\_id → kg\_news\.news\_id|直接|
|HAS\_NODE|产业链包含节点|IndustryChain → IndustryNode|kg\_industry\_chain\.chain\_code → kg\_industry\_node\.node\_id|直接|
|HAS\_OUTPUT<br>|项目产出成果<br>|Project → Paper / Patent / Report<br>|[kg\_project\.id](http://kg_project.id) → [kg\_paper\.id](http://kg_paper.id) / kg\_patent\.patent\_id / kg\_report\.report\_id|展开产出；论文按 DOI→题名＋年→题名，专利按号码→题名，报告按题名＋年→题名匹配。|
|HAS\_PARTICIPANT<br>|项目参与人|Project → Person|[kg\_project\.id](http://kg_project.id) → kg\_person\.person\_id|拆 participants，按人物姓名或 source\_record\_id 唯一匹配。|
|INVENTED\_BY|专利发明人|Patent → Person|kg\_patent\.patent\_id → kg\_person\.person\_id|姓名与任职机构筛出唯一学者；项目证据仅加分。|
|INVESTS\_IN|机构投资|Organization → Organization|kg\_organization\.org\_id → kg\_organization\.org\_id|直接|
|INVOLVED\_IN|机构参与事件|Organization → Event|kg\_organization\.org\_id → kg\_event\.event\_id|直接|
|**CITES**|引用|**Paper（引用方论文）→ Paper（被引用论文）**|起点：kg\_rel\_paper\_citation\.citing\_paper\_id → [kg\_paper\.id](http://kg_paper.id)；<br>终点：kg\_rel\_paper\_citation\.cited\_paper\_id → [kg\_paper\.id](http://kg_paper.id)|直接抽取。 每条记录表示“论文 A 引用了论文 B”，生成 A → CITES → B。两端必须是已经确认的论文编号，不能根据引用次数生成关系。|
|**CITED\_BY**|被引用|**Paper（被引论文）→ Paper（引用它的论文）**|起点：kg\_rel\_paper\_citation\.cited\_paper\_id → [kg\_paper\.id](http://kg_paper.id)；<br>终点：kg\_rel\_paper\_citation\.citing\_paper\_id → [kg\_paper\.id](http://kg_paper.id)|由同一份引用记录反向生成。 对于“A 引用 B”，生成 B → CITED\_BY → A，无需另外补一份反向数据。边属性 citation\_identifier 应标识引用者 A。|
|**COAUTHOR\_WITH**|合著／论文合作|**Person（人物）→ Person（人物）**|起点：`kg_rel_coauthor.scholar_id` → `kg_person.person_id`；<br>终点：`kg_rel_coauthor.co_scholar_id` → `kg_person.person_id`；<br>共同论文数：`kg_rel_coauthor.co_paper_count` → 边属性 `co_paper_count`。|**单表直接抽取。** 每条记录已经明确两个合作人物，直接按编号连接；合作数量直接读取本行，不通过论文作者关系间接计算。|
|**COLLEAGUE**|同事|**Person（人物）→ Person（人物）**<br>|使用 kg\_rel\_person\_org 的两条明确任职记录 a、b，均满足 relation\_kind='employment'：\<\><br>共同机构：a\.org\_id = b\.org\_id，对应 kg\_organization\.org\_id；<br>起点：a\.person\_id → kg\_person\.person\_id；<br>终点：b\.person\_id → kg\_person\.person\_id；<br>任职时间分别取 a\.work\_experience\_date、b\.work\_experience\_date。|间接计算。 先把两条任职记录抽成 Person → AFFILIATED\_WITH → Organization，**并将任职时间写到边属性 **work\_experience\_date。双方是不同人物、机构编号相同、任期有交集时，同事关系才成立。<br>**抽取AFFILIATED\_WITH 关系就行，同事关系查询时计算，但是重叠时间需要边属性提供**<br>|
|**EMPLOYED\_BY**|任职于／受雇于|**Person（人物）→ Organization（机构）**|筛选：kg\_rel\_person\_org\.relation\_kind='employment'；<br>起点：kg\_rel\_person\_org\.person\_id → kg\_person\.person\_id；<br>终点：kg\_rel\_person\_org\.org\_id → kg\_organization\.org\_id。|直接抽取。 每条已确认的任职记录生成一条人物—机构关系。**边属性 relation\_type 由规则赋值为 employment；职位可由补充表的 position 写入边属性 role。**不能把一般机构关联直接当成雇佣。<br>查询时计算入图，同上，需要边属性|
|**EXECUTIVE\_OF**|担任高管|**Person（人物）→ Organization（机构）**<br>|筛选：kg\_rel\_person\_org\.relation\_kind='executive'；<br>起点：kg\_rel\_person\_org\.person\_id → kg\_person\.person\_id；<br>终点：kg\_rel\_person\_org\.org\_id → kg\_organization\.org\_id；<br>职位：kg\_rel\_person\_org\.position → 边属性 position。|多表抽取|
|**FUNDED\_BY**|受资助于|**Project（项目）→ Organization（资助机构）**|起点：kg\_rel\_project\_funder\.project\_id → [kg\_project\.id](http://kg_project.id)；<br>终点：kg\_rel\_project\_funder\.org\_id → kg\_organization\.org\_id。|多表抽取写图（非查询时计算）|
|**HAS\_KEYWORD**|具有关键词|**Paper／Project／Patent（论文／项目／专利）→ Keyword（关键词）**|根据 kg\_rel\_entity\_keyword\.entity\_type 确定起点：<br>paper：entity\_id → [kg\_paper\.id](http://kg_paper.id)；<br>project：entity\_id → [kg\_project\.id](http://kg_project.id)；<br>patent：entity\_id → kg\_patent\.patent\_id；<br>终点：kg\_rel\_entity\_keyword\.keyword\_id → kg\_keyword\.keyword\_id。|多表抽取|
|PRODUCES<br>|生产<br>|Organization（机构）→ Product（产品）<br>|`kg_product.producer_org_ids`（json 内 org id）→ `kg_organization.org_id`|—|
|PUBLISHED\_IN<br>|发表于|Paper（论文）→ Journal（期刊）|`kg_paper.publication_id` → `kg_journal.publication_id`|—|
|RELATED\_TO<br>|相关|Paper（论文）→ Paper（论文）|`kg_paper.related_dois`（json 内 doi）→ `kg_paper.doi`|—|
|SHAREHOLDER\_OF|持股|Organization（机构）→ Organization（机构）<br>|kg\_organization\.shareholders（json 股东清单）：<br>条目含 inv\_org\_id 键 → 其值与 kg\_organization\.org\_id 等值直连（同表自连）；|—<br>|
|STUDIED\_AT<br>|就读于<br>|Person（人物）→ Organization（机构）|—（无直连字段）<br>|间接分析：`kg_person.education_background_institution_zh` / `_en` 院校名与 `kg_organization.name_cn` / `name_en` 精确等值匹配|
|SUBSIDIARY\_OF<br>|子公司/关联方<br>|Organization（机构）→ Organization（机构）<br>|`kg_organization.forg_subsidiaries（json 挂在母公司机构行）：条目 affiliates_company_id 有值 → 与 kg_organization.org_id 等值直连（连到子公司机构行）`|—<br>|
|LEADS<br>|项目负责人|Project（项目） → Person（人物）<br>|kg\_project\.project\_host → kg\_person\.name\_cn/name\_zh/name\_en<br>|间接分析：<br>kg\_project\.project\_host → 拆名（中文多值逐个拆、英文名不拆） → 与 kg\_person\.name\_cn / name\_zh / name\_en 精确且唯一匹配 → 命中且唯一 → 写边|
|LEGAL\_REP\_OF<br>|法定代表人|Person（人物） → Organization（机构）|kg\_person\.organization\_id → kg\_organization\.org\_id|—|
|MEMBER\_OF\_FAMILY<br>|专利同族|Patent（专利） → PatentFamily（专利同族）|kg\_patent\.simple\_family\_number →  kg\_patent\_family\.family\_number|—<br>|
|ACQUIRES<br>|收购|Organization → Organization<br>|kg\_organization\.acquires→ kg\_organization\.org\_id|起点=acquiring\_org\_id，终点=acquired\_org\_id；ma\_amount/currency\_code 作边属性直接带出|
|ACTUAL\_CONTROLLER\_OF|实际控制|Person → Organization|kg\_organization\.actual\_controllers（json 内 endpoint\_vid）→ kg\_organization\.org\_id|间接（人名消歧）：源表 dwd\_forg\_act\_contro\_info 机构侧 org\_id 直连，人侧只有姓名，建桩\+词表过滤。使用业务：2、7、8|
|AFFILIATED\_WITH<br>|任职|Person → ScholarOrganization|kg\_person\.affiliation\_org\_ids（json 内 org\_id）→ kg\_scholar\_organization\.org\_id|间接（机构名消歧）：dwd\_scholar\_work\_experience 只有机构名无 ID——scholar\_org\_id 直连优先（confidence=1\.0），名称匹配 0\.6 分桩待认领。使用业务：2、4、7、8（模块 9 作可选筛选项）|
|APPLIED\_BY<br>|专利申请|Patent → Organization|建成后通道 kg\_edge src 去 `patent_` → kg\_patent\.patent\_id，dst 去 `org_` → kg\_organization\.org\_id|间接（挂实体改道）：dwd\_patent\.first\_applicant\_name 姓名/机构名解析——图内唯一同名机构直连（confidence 0\.98，164 条自动命中）；歧义/无同名走 pendingReview 人工裁决（约 1,836 个申请人），当前被 techkg\_global 目录门控阻塞待修复。使用业务：2、7|
|AUTHORED\_BY|论文署名|Paper → Person|kg\_paper\.author\_ids（json 内 person\_id）→ kg\_person\.person\_id|paper\_id→Paper、author\_id→Person；author\_sequence→署名序、correspond→通讯作者。（另有dwd\_scholar\_paper\_relation 作 paper\_id\+scholar\_id 兜底）|
|BELONGS\_TO\_NODE<br>|企业归属产业节点<br>|Organization → IndustryNode<br>|kg\_organization\.industry\_node\_ids（json 内 node\_id \+ chain\_score）→ kg\_industry\_node\.node\_id|间接（JSON 标签炸开\+打分）：机构\-产业标签 JSON 按编码位数展开，chain\_score 为打分结果非一对一。使用业务：2、8、9|
|BENEFICIAL\_OWNER\_OF<br>|最终受益<br>|Person → Organization<br>|kg\_organization\.beneficial\_owners（json 内 person\_id）→ kg\_person\.person\_id|间接（人名消歧）：同 20——机构侧 org\_id 直连，人侧 bo\_name 建桩\+词表过滤。使用业务：2、7、8|



