# 报告字段规范

来源数据库：`gkx`
生成日期：`2026-06-25`

| 表名 | 表注释 | 估算行数 | 字段数 |
|---|---|---:|---:|
| `ods_en_report` | 万方外文报告信息 | 899 | 32 |
| `ods_zh_report` | 万方中文报告信息 | 140 | 29 |

## `ods_en_report`

表注释：万方外文报告信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `Identifier_ID` | `varchar(50)` | YES |  |  |  |  |
| 2 | `Report_Num` | `varchar(50)` | YES |  |  |  |  |
| 3 | `Title_Title` | `text` | YES |  |  |  |  |
| 4 | `Title_AlterNativeTitle` | `text` | YES |  |  |  |  |
| 5 | `Creator_Creator` | `text` | YES |  |  |  |  |
| 6 | `Creator_AlterNativeCreator` | `text` | YES |  |  |  |  |
| 7 | `Creator_Org` | `text` | YES |  |  |  |  |
| 8 | `Creator_AlterNativeOrg` | `text` | YES |  |  |  |  |
| 9 | `Date_Issued` | `varchar(50)` | YES |  |  |  |  |
| 10 | `Description_Abstract` | `text` | YES |  |  |  |  |
| 11 | `Description_AlternativeAbstract` | `text` | YES |  |  |  |  |
| 12 | `Subject_Keywords` | `text` | YES |  |  |  |  |
| 13 | `Subject_AlternativeKeywords` | `text` | YES |  |  |  |  |
| 14 | `Subject_CLC` | `text` | YES |  |  |  |  |
| 15 | `Subject_SelfFL` | `text` | YES |  |  |  |  |
| 16 | `Report_Source` | `varchar(50)` | YES |  |  |  |  |
| 17 | `Language_Language` | `varchar(50)` | YES |  |  |  |  |
| 18 | `Place_Counry` | `varchar(50)` | YES |  |  |  |  |
| 19 | `Source_Page` | `varchar(512)` | YES |  |  |  |  |
| 20 | `Source_PageCount` | `varchar(50)` | YES |  |  |  |  |
| 21 | `Yn_publition` | `varchar(50)` | YES |  |  |  |  |
| 22 | `Report_Type` | `varchar(50)` | YES |  |  |  |  |
| 23 | `Publisher_Publisher` | `varchar(50)` | YES |  |  |  |  |
| 24 | `f_id` | `varchar(50)` | YES |  |  |  |  |
| 25 | `Date_Download` | `varchar(50)` | YES |  |  |  |  |
| 26 | `DataLink` | `text` | YES |  |  |  |  |
| 27 | `Collection_Number` | `varchar(50)` | YES |  |  |  |  |
| 28 | `Document_Type` | `varchar(50)` | YES |  |  |  |  |
| 29 | `Sponsor` | `varchar(50)` | YES |  |  |  |  |
| 30 | `IS_OA` | `varchar(50)` | YES |  |  |  |  |
| 31 | `F_Publish_Date` | `varchar(512)` | YES |  |  |  |  |
| 32 | `F_FulltextUrl` | `text` | YES |  |  |  |  |

## `ods_zh_report`

表注释：万方中文报告信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `title` | `text` | YES |  |  |  |  |
| 2 | `alternativeTitle` | `text` | YES |  |  |  |  |
| 3 | `creator` | `text` | YES |  |  |  |  |
| 4 | `creatOrorganization` | `text` | YES |  |  |  |  |
| 5 | `prepareOrganization` | `text` | YES |  |  |  |  |
| 6 | `publicScope` | `int` | YES |  |  |  |  |
| 7 | `publicDate` | `varchar(50)` | YES |  |  |  |  |
| 8 | `delaypubliclyYears` | `int` | YES |  |  |  |  |
| 9 | `note` | `varchar(50)` | YES |  |  |  |  |
| 10 | `abstractCn` | `text` | YES |  |  |  |  |
| 11 | `proposalDate` | `varchar(50)` | YES |  |  |  |  |
| 12 | `downtime` | `varchar(50)` | YES |  |  |  |  |
| 13 | `keywordsCn` | `text` | YES |  |  |  |  |
| 14 | `keywordsEn` | `text` | YES |  |  |  |  |
| 15 | `abstractEn` | `text` | YES |  |  |  |  |
| 16 | `projectName` | `varchar(256)` | YES |  |  |  |  |
| 17 | `projectSubjectName` | `text` | YES |  |  |  |  |
| 18 | `competentOrg` | `varchar(50)` | YES |  |  |  |  |
| 19 | `responsiblePerson` | `varchar(50)` | YES |  |  |  |  |
| 20 | `startDate` | `varchar(50)` | YES |  |  |  |  |
| 21 | `endDate` | `varchar(50)` | YES |  |  |  |  |
| 22 | `linkmanName` | `varchar(50)` | YES |  |  |  |  |
| 23 | `linkmanEmail` | `varchar(50)` | YES |  |  |  |  |
| 24 | `lnkmanPhone` | `varchar(50)` | YES |  |  |  |  |
| 25 | `linkmanAddresss` | `text` | YES |  |  |  |  |
| 26 | `fieldId` | `text` | YES |  |  |  |  |
| 27 | `classification` | `varchar(50)` | YES |  |  |  |  |
| 28 | `kjbgType` | `varchar(50)` | YES |  |  |  |  |
| 29 | `ID` | `varchar(50)` | YES |  |  |  |  |
