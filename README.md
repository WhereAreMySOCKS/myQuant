# Investment Guard V3 — API 接口文档

> A股投资监控系统：个股 / ETF / 场外基金 实时监控 + 买卖信号报警

- **Base URL**：`http://localhost:8000`
- **数据格式**：JSON
- **字符编码**：UTF-8

---

## 目录

- [1. 系统状态](#1-系统状态)
  - [1.1 健康检查](#11-健康检查)
- [2. 关注管理](#2-关注管理)
  - [2.1 新增关注标的](#21-新增关注标的)
  - [2.2 批量新增关注](#22-批量新增关注)
  - [2.3 获取所有关注标的](#23-获取所有关注标的)
  - [2.4 查询单个标的](#24-查询单个标的)
  - [2.5 修改标的阈值](#25-修改标的阈值)
  - [2.6 删除关注标的](#26-删除关注标的)
- [3. 行情查询](#3-行情查询)
  - [3.1 查询实时行情 / 估值](#31-查询实时行情--估值)
- [附录 A：数据模型](#附录-a数据模型)
- [附录 B：枚举值](#附录-b枚举值)
- [附录 C：错误码](#附录-c错误码)

---

## 1. 系统状态

### 1.1 健康检查

获取系统运行状态、当前是否为交易时间、已关注标的数量。

```
GET /
```

#### 请求参数

无

#### 响应示例

```json
{
  "status": "active",
  "trading_time": true,
  "monitored_count": 5
}
```

#### 响应字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | 系统状态，固定值 `"active"` |
| `trading_time` | boolean | 当前是否为 A 股交易时间（工作日 09:30–11:30, 13:00–15:00） |
| `monitored_count` | integer | 当前已关注的标的总数 |

---

## 2. 关注管理

> 路由前缀：`/targets`

### 2.1 新增关注标的

添加一个需要监控的个股、ETF 或场外基金。

```
POST /targets/
```

#### 请求头

| Header | 值 |
|--------|----|
| Content-Type | application/json |

#### 请求体

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `code` | string | ✅ | 标的代码，如 `"600519"`、`"510300"`、`"012708"` |
| `buy_bias_rate` | float | ❌ | 个股/ETF 乖离率买入阈值，如 `-0.08` 表示低于年线 8% 时触发���入信号 |
| `sell_bias_rate` | float | ❌ | 个股/ETF 乖离率卖出阈值，如 `0.15` 表示高于年线 15% 时触发卖出信号 |
| `buy_growth_rate` | float | ❌ | 场外基金估算跌幅买入阈值，如 `-2.0` 表示估算跌 2% 时触发 |
| `sell_growth_rate` | float | ❌ | 场外基金估算涨幅卖出阈值，如 `3.0` 表示估算涨 3% 时触发 |

> **阈值说明**：
> - `stock` / `etf` 类型应设置 `buy_bias_rate` 和 `sell_bias_rate`
> - `otc` 类型应设置 `buy_growth_rate` 和 `sell_growth_rate`
> - 未设置阈值的标的不会触发对应方向的信号

#### 请求示例

**个股：**

```json
{
  "code": "600519",
  "buy_bias_rate": -0.08,
  "sell_bias_rate": 0.15
}
```

**ETF：**

```json
{
  "code": "510300",
  "buy_bias_rate": -0.05,
  "sell_bias_rate": 0.10
}
```

**场外基金：**

```json
{
  "code": "012708",
  "buy_growth_rate": -2.0,
  "sell_growth_rate": 3.0
}
```

#### 成功响应 `200 OK`

```json
{
  "id": 1,
  "code": "600519",
  "name": "贵州茅台",
  "type": "stock",
  "buy_bias_rate": -0.08,
  "sell_bias_rate": 0.15,
  "buy_growth_rate": null,
  "sell_growth_rate": null
}
```

#### 错误响应 `400 Bad Request`

```json
{
  "detail": "标的 600519 已存在"
}
```

---

### 2.2 批量新增关注

一次性添加多个标的，已存在的会自动跳过（不报错）。

```
POST /targets/batch
```

#### 请求体

类型：`TargetCreate[]`（数组），每个元素的字段与 [2.1 新增关注标的](#21-新增关注标的) 相同。

#### 请求示例

```json
[
  {
    "code": "600519",
    "name": "贵州茅台",
    "type": "stock",
    "buy_bias_rate": -0.08,
    "sell_bias_rate": 0.15
  },
  {
    "code": "510300",
    "name": "沪深300ETF",
    "type": "etf",
    "buy_bias_rate": -0.05,
    "sell_bias_rate": 0.10
  },
  {
    "code": "012708",
    "name": "东方红启恒",
    "type": "otc",
    "buy_growth_rate": -2.0,
    "sell_growth_rate": 3.0
  }
]
```

#### 成功响应 `200 OK`

返回**实际新增成功**的标的列表（已存在的不包含在内）：

```json
[
  {
    "id": 1,
    "code": "600519",
    "name": "贵州茅台",
    "type": "stock",
    "buy_bias_rate": -0.08,
    "sell_bias_rate": 0.15,
    "buy_growth_rate": null,
    "sell_growth_rate": null
  },
  {
    "id": 2,
    "code": "510300",
    "name": "沪深300ETF",
    "type": "etf",
    "buy_bias_rate": -0.05,
    "sell_bias_rate": 0.10,
    "buy_growth_rate": null,
    "sell_growth_rate": null
  },
  {
    "id": 3,
    "code": "012708",
    "name": "东方红启恒",
    "type": "otc",
    "buy_bias_rate": null,
    "sell_bias_rate": null,
    "buy_growth_rate": -2.0,
    "sell_growth_rate": 3.0
  }
]
```

---

### 2.3 获取所有关注标的

查询当前所有已关注的标的列表。

```
GET /targets/
```

#### 请求参数

无

#### 成功响应 `200 OK`

```json
[
  {
    "id": 1,
    "code": "600519",
    "name": "贵州茅台",
    "type": "stock",
    "buy_bias_rate": -0.08,
    "sell_bias_rate": 0.15,
    "buy_growth_rate": null,
    "sell_growth_rate": null
  },
  {
    "id": 2,
    "code": "012708",
    "name": "东方红启恒",
    "type": "otc",
    "buy_bias_rate": null,
    "sell_bias_rate": null,
    "buy_growth_rate": -2.0,
    "sell_growth_rate": 3.0
  }
]
```

> 如果没有任何关注标的，返回空数组 `[]`。

---

### 2.4 查询单个标的

根据标的代码查询详情。

```
GET /targets/{code}
```

#### 路径参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `code` | string | 标的代码，如 `600519` |

#### 成功响应 `200 OK`

```json
{
  "id": 1,
  "code": "600519",
  "name": "贵州茅台",
  "type": "stock",
  "buy_bias_rate": -0.08,
  "sell_bias_rate": 0.15,
  "buy_growth_rate": null,
  "sell_growth_rate": null
}
```

#### 错误响应 `404 Not Found`

```json
{
  "detail": "标的 600519 不存在"
}
```

---

### 2.5 修改标的阈值

修改已关注标的的名称或买卖阈值，仅传需要修改的字段即可。

```
PUT /targets/{code}
```

#### 路径参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `code` | string | 标的代码 |

#### 请求体（部分更新）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ❌ | 新名称 |
| `buy_bias_rate` | float | ❌ | 新的乖离率买入阈值 |
| `sell_bias_rate` | float | ❌ | 新的乖离率卖出阈值 |
| `buy_growth_rate` | float | ❌ | 新的估算跌幅买入阈值 |
| `sell_growth_rate` | float | ❌ | 新的估算涨幅卖出阈值 |

> 仅传入需要修改的字段，未传入的字段保持不变。

#### 请求示例

将买入乖离率阈值从 `-0.08` 改为 `-0.10`：

```json
{
  "buy_bias_rate": -0.10
}
```

#### 成功响应 `200 OK`

返回修改后的完整标的信息：

```json
{
  "id": 1,
  "code": "600519",
  "name": "贵州茅台",
  "type": "stock",
  "buy_bias_rate": -0.10,
  "sell_bias_rate": 0.15,
  "buy_growth_rate": null,
  "sell_growth_rate": null
}
```

#### 错误响应 `404 Not Found`

```json
{
  "detail": "标的 600519 不存在"
}
```

---

### 2.6 删除关注标的

取消关注某个标的，删除后将不再监控。

```
DELETE /targets/{code}
```

#### 路径参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `code` | string | 标的代码 |

#### 成功响应 `200 OK`

```json
{
  "message": "已删除 600519"
}
```

#### 错误响应 `404 Not Found`

```json
{
  "detail": "标的 600519 不存在"
}
```

---

## 3. 行情查询

### 3.1 查询实时行情 / 估值

统一行情查询入口，根据标的类型和当前时段自动返回不同数据。

```
GET /quote/{code}
```

#### 路径参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `code` | string | 已关注的标的代码 |

> **前置条件**：标的必须已通过 `/targets/` 接口添加关注，否则返回 404。

#### 行为逻辑

| 标的类型 | 交易时间内 | 非交易时间 |
|---------|-----------|-----------|
| `stock` | 返回实时价格 + 技术指标（MA5/MA20/MA250/乖离率） | 返回最近收盘价 |
| `etf` | 返回实时价格 + 技术指标 | 返回最近收盘价 |
| `otc` | 返回实时估值（估算净值 + 估算涨跌幅） | 返回最近确认净值 |

---

#### 响应示例：个股/ETF — 交易时间内

`status` = `"realtime"`

```json
{
  "code": "600519",
  "name": "贵州茅台",
  "type": "stock",
  "status": "realtime",
  "realtime": {
    "price": 1688.50,
    "change_pct": 1.25,
    "volume": 23456.0,
    "amount": 39012345.0,
    "high": 1695.00,
    "low": 1670.00,
    "open": 1675.00,
    "pre_close": 1667.60
  },
  "indicators": {
    "price": 1688.5,
    "ma5": 1680.32,
    "ma20": 1665.78,
    "ma250": 1580.45,
    "bias_rate": 0.0684,
    "bias_percent": "6.84%"
  }
}
```

#### 响应示例：个股/ETF — 非交易时间

`status` = `"closed"`

```json
{
  "code": "600519",
  "name": "贵州茅台",
  "type": "stock",
  "status": "closed",
  "close_price": 1688.50,
  "close_date": "2026-02-24"
}
```

#### 响应示例：场外基金 — 交易时间内

`status` = `"estimation"`

```json
{
  "code": "012708",
  "name": "东方红启恒",
  "type": "otc",
  "status": "estimation",
  "data": {
    "nav": 1.2345,
    "growth_rate": -1.58,
    "time": "2026-02-24 14:30:00"
  }
}
```

#### 响应示例：场外基金 — 非交易时间

`status` = `"closed"`

```json
{
  "code": "012708",
  "name": "东方红启恒",
  "type": "otc",
  "status": "closed",
  "data": {
    "nav": 1.2500,
    "date": "2026-02-23"
  }
}
```

#### 响应字段说明

**顶层字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | string | 标的代码 |
| `name` | string | 标的名称 |
| `type` | string | 标的类型：`"stock"` / `"etf"` / `"otc"` |
| `status` | string | 数据状态：`"realtime"` / `"estimation"` / `"closed"` |
| `realtime` | object \| null | 实时行情数据（仅 stock/etf 交易时间） |
| `indicators` | object \| null | 技术指标（仅 stock/etf 交易时间） |
| `data` | object \| null | 场外基金数据（仅 otc） |
| `close_price` | float \| null | 收盘价（仅 stock/etf 非交易时间） |
| `close_date` | string \| null | 收盘日期（仅 stock/etf 非交易时间） |

**`realtime` 对象（个股）：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `price` | float | 最新价 |
| `change_pct` | float | 涨跌幅（%） |
| `volume` | float | 成交量 |
| `amount` | float | 成交额 |
| `high` | float | 最高价 |
| `low` | float | 最低价 |
| `open` | float | 开盘价 |
| `pre_close` | float | 昨收价 |

**`realtime` 对象（ETF）：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `price` | float | 最新价 |
| `change_pct` | float | 涨跌幅（%） |

**`indicators` 对象：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `price` | float | 当前价格 |
| `ma5` | float | 5 日均线 |
| `ma20` | float | 20 日均线 |
| `ma250` | float | 250 日均线（年线） |
| `bias_rate` | float | 乖离率（小数），如 `0.0684` 表示高于年线 6.84% |
| `bias_percent` | string | 乖离率（百分比格式），如 `"6.84%"` |

**`data` 对象（场外 — 交易时间内）：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `nav` | float | 估算净值 |
| `growth_rate` | float | 估算涨跌幅（%） |
| `time` | string | 估值更新时间 |

**`data` 对象（场外 — 非交易时间）：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `nav` | float | 确认净值 |
| `date` | string | 净值确认日期 |

#### 错误响应 `404 Not Found`

标的未关注：

```json
{
  "detail": "标的 012708 未关注，请先添加"
}
```

数据获取失败：

```json
{
  "detail": "数据获取失败"
}
```

---

## 附录 A：数据模型

### TargetCreate（创建请求）

```json
{
  "code": "string (必填)",
  "name": "string (必填)",
  "type": "string (必填): stock | etf | otc",
  "buy_bias_rate": "float (选填)",
  "sell_bias_rate": "float (选填)",
  "buy_growth_rate": "float (选填)",
  "sell_growth_rate": "float (选填)"
}
```

### TargetUpdate（更新请求）

```json
{
  "name": "string (选填)",
  "buy_bias_rate": "float (选填)",
  "sell_bias_rate": "float (选填)",
  "buy_growth_rate": "float (选填)",
  "sell_growth_rate": "float (选填)"
}
```

### TargetResponse（标的响应）

```json
{
  "id": "integer",
  "code": "string",
  "name": "string",
  "type": "string",
  "buy_bias_rate": "float | null",
  "sell_bias_rate": "float | null",
  "buy_growth_rate": "float | null",
  "sell_growth_rate": "float | null"
}
```

---

## 附录 B：枚举值

### 标的类型 `TargetTypeEnum`

| 值 | 说明 | 监控方式 | 适用阈值 |
|----|------|---------|---------|
| `stock` | A 股个股 | 实时价 → MA250 乖离率 | `buy_bias_rate` / `sell_bias_rate` |
| `etf` | 场内 ETF | 实时价 → MA250 乖离率 | `buy_bias_rate` / `sell_bias_rate` |
| `otc` | 场外基金 | 实时估值 → 估算涨跌幅 | `buy_growth_rate` / `sell_growth_rate` |

### 行情状态 `status`

| 值 | 说明 |
|----|------|
| `realtime` | 交易时间内，返回个股/ETF 实时数据 |
| `estimation` | 交易时间内，返回场外基金实时估值 |
| `closed` | 非交易时间，返回收盘/确认数据 |

### 交易信号 `signal`

| 值 | 说明 |
|----|------|
| `BUY` | 买入信号：乖离率 ≤ 买入阈值，或估算涨跌 ≤ 买入阈值 |
| `SELL` | 卖出信号：乖离率 ≥ 卖出阈值，或估算涨跌 ≥ 卖出阈值 |

> 信号判断优先级：卖出 > 买入（保守策略，优先止盈/止损）。
> 每个标的每天每个方向最多触发一次报警邮件。

---

## 附录 C：错误码

系统遵循标准 HTTP 状态码 + FastAPI 默认错误格式。

| 状态码 | 场景 | 响应体示例 |
|--------|------|-----------|
| `200` | 请求成功 | 见各接口响应示例 |
| `400` | 业务校验失败（如标的已存在） | `{"detail": "标的 600519 已存在"}` |
| `404` | 资源不存在（标的未找到 / 数据获取失败） | `{"detail": "标的 600519 不存在"}` |
| `422` | 请求体格式错误 / 字段校验失败 | FastAPI 自动生成的 ValidationError |

### `422` 错误示例

缺少必填字段：

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "code"],
      "msg": "Field required",
      "input": {}
    }
  ]
}
```

枚举值不合法：

```json
{
  "detail": [
    {
      "type": "enum",
      "loc": ["body", "type"],
      "msg": "Input should be 'stock', 'etf' or 'otc'",
      "input": "bond"
    }
  ]
}
```