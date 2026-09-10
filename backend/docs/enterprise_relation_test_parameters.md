# 重点关注科技企业关系测试参数

> 以下数据仅供测试老师执行接口和页面测试，不再预填到页面输入框。

接口：`POST /api/v1/kg-service/key-enterprise-relation`

## 参数要求

- `expert_id`：必填，科技专家唯一标识 VID。
- `enterprise_name`：可选；企业名称模糊筛选，留空不筛。
- `role_type`：可选；专家企业角色筛选（如「总经理」），留空不筛。
- `industry`：可选；企业行业方向筛选，留空不筛。
- `key_tech_enterprise_only`：可选；只保留重点科技企业（已上市/公司类，排除高校/研究院/MOCK）。传布尔 `true`/`false`，默认 `true`。下拉选择，留空走默认。

## 第一组：宋震 → 徐工集团（已上市，推荐）

- 专家：宋震（`person_94447y38`），任徐工集团工程机械股份有限公司（000425.SZ）研究员。
- 关系类型：governance（任职 / 治理任职）。
- 实测结果：`enterprises=1`，合作时间 `2020-06 至 2024-12`，`confidence=0.9`。默认 `key_tech_enterprise_only=true` 即可命中。

```json
{
  "expert_id": "person_94447y38"
}
```

## 第二组：陈威 → 深圳市意天科技（公司类，需关闭重点筛选）

- 专家：陈威（`person_998k67K0`），任深圳市意天科技有限公司助理研究员。
- 关系类型：governance（任职）。
- 实测结果：`key_tech_enterprise_only=false` 时 `enterprises=1`，合作时间 `2020-07 至 2024-12`，技术方向取自主营产品。

```json
{
  "expert_id": "person_998k67K0",
  "key_tech_enterprise_only": false
}
```

## 第三组：李俊 → 北京航空材料研究院（验证重点企业筛选）

- 专家：李俊（`person_835Q3o89`），任北京航空材料研究院股份有限公司（名称含「研究院」）。
- 重点：该企业虽已上市，但名称含「研究院」关键字，`key_tech_enterprise_only=true` 时被排除。
- 实测结果：`key_tech_enterprise_only=true` → `enterprises=0`（被筛掉）；`key_tech_enterprise_only=false` → 视图谱边是否存在而定。

```json
{
  "expert_id": "person_835Q3o89",
  "key_tech_enterprise_only": false
}
```

## 页面校验点

- 首次进入页面时，输入框均为空；`expert_id` 占位提示为「示例：person_94447y38（宋震）」。
- 点击「重置参数」后，所有输入框恢复为空。
- `expert_id` 为空时，字段下方显示「请输入专家唯一标识」，页面提示「请完善必填项后再执行」，不发起请求。
- 五个入参排成一行（单行布局）。
- 第一组应返回 1 家关联重点科技企业；第二组需将「只保留重点科技企业」改为 `false` 才返回 1 家。
