# 重点关注科技企业关系测试参数

> 以下数据仅供测试老师执行接口和页面测试，不再预填到页面输入框。

接口：`POST /api/v1/kg-service/key-enterprise-relation`

## 参数要求

- `expert_id`：必填，科技专家唯一标识 VID。
- `enterprise_name`：可选；企业名称模糊筛选，留空不筛。
- `role_type`：可选；专家企业角色筛选（如「总经理」），留空不筛。
- `industry`：可选；企业行业方向筛选，留空不筛。
- `key_tech_enterprise_only`：可选；只保留重点科技企业（已上市/公司类，排除高校/研究院/MOCK）。传 `是`/`否`，默认 `是`。下拉选择，留空走默认。

## 第一组：郭佳佳 → 新智认知数字科技（已上市）

- 专家：郭佳佳（person_855924f1），任新智认知数字科技股份有限公司（688017.SH）任职。
- 关系类型：governance（任职）。
- 实测结果：`enterprises=1`，`role_level=null`，`confidence=0.9`，合作时间 `2019-01 至 2024-12`。

```json
{
  "expert_id": "person_855924f1"
}
```

## 第二组：蒋宜里 → 深圳市意天科技（公司类）

- 专家：蒋宜里（person_38d2c013d911a0546d97fb493f7bcbc4），任深圳市意天科技有限公司总经理/执行董事。
- 关系类型：governance（高管任职）。
- 实测结果：`enterprises=1`（同一企业多条边按 enterprise_id 去重），`roles=2`，其中 `总经理→L1`、`执行董事→null`，`confidence=0.9`。

```json
{
  "expert_id": "person_38d2c013d911a0546d97fb493f7bcbc4"
}
```

## 第三组：李俊 → 北京航空材料研究院（验证重点企业筛选）

- 专家：李俊（person_835Q3o89），任北京航空材料研究院股份有限公司（688563.SH 已上市，但名称含「研究院」）。
- 重点：该企业虽已上市，但名称含「研究院」关键字，`key_tech_enterprise_only=是` 时被排除。
- 实测结果：`key_tech_enterprise_only=是` → `enterprises=0`（被筛掉）；`key_tech_enterprise_only=否` → `enterprises=1`（保留，cooperation_mode=任职）。

```json
{
  "expert_id": "person_835Q3o89",
  "key_tech_enterprise_only": "否"
}
```

## 页面校验点

- 首次进入页面时，五个输入框均为空（`key_tech_enterprise_only` 下拉默认显示占位提示「只保留重点科技企业（默认是）」）。
- 点击「重置参数」后，所有输入框恢复为空。
- `expert_id` 为空时，字段下方显示「请输入专家唯一标识」，页面提示「请完善必填项后再执行」，不发起请求。
- 五个入参排成一行（单行布局）。
- 第一、二组应返回 1 家关联重点科技企业；第三组按 `key_tech_enterprise_only` 取值不同，`是` 返回 0、`否` 返回 1，验证筛选生效。
