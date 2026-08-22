# 科技产业链点 TOP-N 事件关系测试参数

> 以下数据仅供测试老师执行接口和页面测试，不再预填到页面输入框。

接口：`POST /api/v1/kg-service/industry-node-top-events`

## 参数要求

- `chain_node_id`：必填，产业链节点标识（如 `IC0007007` 集成电路设计）。
- `top_n`：可选；返回事件数量，取值 `1-50`，默认 `10`。
- `event_type`：可选；事件类型筛选（`financing`/`bankruptcy`/`bid`/`news`/…），留空不筛。
- `time_range_start` / `time_range_end`：可选；起止年月，下拉选择日期，留空不筛。两端会自动合并为年份区间传给后端（如选 `2025-01` 至 `2026-12` → 等效 `2025-2026`）。
- `max_orgs`：可选；链节点下最多扫描企业数（按 chain_score 排序），取值 `1-50`，默认 `20`。

## 第一组：集成电路设计 TOP 10

- 节点：IC0007007（集成电路设计，node_imp_level=1）。
- 实测结果：`events=10`，`enterprises=160`，`risk_level=中`，`confidence=0.75`；TOP 事件以 `stock_finance`/`annual_finance` 为主，impact_score 降序。

```json
{
  "chain_node_id": "IC0007007"
}
```

## 第二组：限定 TOP 5

- 节点：IC0007007。
- 实测结果：`events=5`，按影响力降序取前 5。

```json
{
  "chain_node_id": "IC0007007",
  "top_n": 5
}
```

## 第三组：按事件类型 + 年份区间筛选

- 节点：IC0007007。
- 筛选：`event_type=stock_finance`，时间 `2025-01` 至 `2026-12`（等效 `2025-2026`）。
- 实测结果：仅返回 `event_type=stock_finance` 事件；将起止年月改为 `2010-01` 至 `2011-12` 时 `events=0`（该区间无事件），验证筛选生效。

```json
{
  "chain_node_id": "IC0007007",
  "top_n": 10,
  "event_type": "stock_finance",
  "time_range_start": "2025-01",
  "time_range_end": "2026-12"
}
```

## 页面校验点

- 首次进入页面时，六个输入框均为空（`top_n`/`event_type`/`time_range_start`/`time_range_end`/`max_orgs` 占位提示见输入框）。
- 点击「重置参数」后，所有输入框恢复为空。
- `chain_node_id` 为空时，字段下方显示「请输入产业链节点标识」，页面提示「请完善必填项后再执行」，不发起请求。
- `time_range_start`/`time_range_end` 为下拉日期选择（月份），与「科技专家同事关系」的时间选择 UI 一致。
- `top_n`、`max_orgs` 描述标注取值范围 `1-50`；超出范围的值由后端参数校验返回 422（HTTP 200 + body.code=422）。
- 六个入参排成一行（单行布局，桌面宽屏下单行排满）。
