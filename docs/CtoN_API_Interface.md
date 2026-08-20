# CtoN API 接口文档

版本：1.0  
项目：CtoN（Chongqing to Nanjing）  
后端：Python + FastAPI  
数据源：和风天气 API（暂定）  
地图：高德地图 API（暂定）  
AI：DeepSeek API（暂定）

## 1. 接口目标

本接口为 Vue 前端提供以下能力：

- 获取重庆至南京高铁线路和城市节点；
- 获取城市天气、空气质量和大气稳定度；
- 获取沿线温度、湿度、AQI、风速剖面；
- 随机选择一个沿线城市进行气象旅行；
- 根据城市天气图片显示前端预设诗句；
- 生成并查询全线路天气旅途建议。

前端只访问 CtoN 后端接口，不直接调用和风天气、DeepSeek。地图展示使用高德地图 JavaScript SDK，路线和城市数据由 CtoN 后端提供。地图安全服务请求经同源 `/_AMapService/` 代理转发；它不是业务 API。

## 2. 基础约定

### 2.1 基础 URL

开发环境：

```text
http://localhost:8000/api/v1
```

生产环境示例：

```text
https://cton.example.com/api/v1
```

所有接口使用 HTTPS（本地开发除外），请求和响应编码为 UTF-8。

### 2.2 请求头

```http
Accept: application/json
Content-Type: application/json
X-Request-ID: 7e6c1a4b-4e03-4f69-a5f4-4b8df7a11d20
```

`X-Request-ID` 由前端可选传入。未传入时由后端生成，并在响应头中原样返回，用于日志排查。

公网 GET 接口不需要身份凭据。两个管理 POST 必须额外携带：

```http
Authorization: Bearer <ADMIN_API_TOKEN>
```

令牌缺失或错误时返回 `401`、业务码 `40100`，并包含 `WWW-Authenticate: Bearer`。开发环境未配置管理员令牌时返回 `503`、业务码 `50300`。前端不得读取或保存该令牌。

内部 Cron GET 使用独立凭据：

```http
Authorization: Bearer <CRON_SECRET>
```

`CRON_SECRET` 不得与管理员令牌相同。缺失、未配置或错误时统一返回 `40100` 和 `WWW-Authenticate: Bearer`。

### 2.3 日期和单位

| 内容 | 格式 |
|---|---|
| 日期参数 | `YYYY-MM-DD`，如 `2026-07-30` |
| 时间字段 | UTC ISO 8601，如 `2026-07-30T08:00:00Z` |
| 温度 | °C |
| 湿度、降水概率 | % |
| 风速 | m/s |
| 距离、能见度 | km |
| 气压 | hPa |
| 太阳高度角 | ° |
| 污染物浓度 | µg/m³ |

日期不传时，查询接口默认使用 `APP_TIMEZONE` 对应的当前日期，默认时区为 `Asia/Shanghai`。当前动态数据只保留最近 15 个自然日，超出范围返回 `422`。

## 3. 统一响应格式

### 3.1 成功响应

```json
{
  "code": 0,
  "message": "ok",
  "data": {},
  "request_id": "7e6c1a4b-4e03-4f69-a5f4-4b8df7a11d20"
}
```

约定：

- `code: 0` 表示成功；
- `message` 为简短结果说明，前端不应依赖文字判断业务状态；
- 具体业务内容都放在 `data` 中；
- 列表统一使用数组，即使当前只有一条记录；
- 空结果使用 `[]` 或 `null`，不使用字符串 `""` 表示空值；
- 可选数值没有数据时返回 `null`，不使用 `0` 代替。

### 3.2 分页响应

目前列表数据量较小，线路和城市接口不分页。需要分页的接口统一使用以下结构：

```json
{
  "items": [],
  "page": 1,
  "page_size": 20,
  "total": 0
}
```

### 3.3 错误响应

```json
{
  "code": 40001,
  "message": "请求参数校验失败",
  "data": {
    "field_errors": [
      {
        "field": "date",
        "reason": "日期格式必须为 YYYY-MM-DD"
      }
    ]
  },
  "request_id": "7e6c1a4b-4e03-4f69-a5f4-4b8df7a11d20"
}
```

错误码：

| HTTP 状态码 | 业务码 | 说明 |
|---:|---:|---|
| 400 | `40000` | 请求格式错误 |
| 400 | `40001` | 参数校验失败 |
| 401 | `40100` | 管理员凭据缺失或错误 |
| 404 | `40401` | 资源不存在 |
| 409 | `40901` | 资源状态冲突 |
| 422 | `42201` | 日期超出 15 天数据范围 |
| 429 | `42901` | 请求过于频繁 |
| 502 | `50201` | 天气/地图/AI 外部服务失败 |
| 503 | `50300` | 后端服务暂时不可用或开发环境未配置管理员令牌 |
| 500 | `50000` | 未预期的服务器错误 |

前端只根据 HTTP 状态码和 `code` 分支处理，不解析 `message`。发生错误时展示可读提示，并保留 `request_id` 便于反馈问题。

## 4. 后端接口定义

### 4.1 服务健康检查

#### `GET /health`

用于部署探活，不访问外部 API。

响应：`200 OK`

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "status": "ok",
    "database": "ok",
    "version": "1.0.0"
  },
  "request_id": "health-001"
}
```

### 4.2 获取线路列表

#### `GET /routes`

首页初始化时调用，默认只返回启用线路。

查询参数：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---:|---|---|
| `active_only` | boolean | 否 | `true` | 是否只返回启用线路 |

响应 `data`：

```json
[
  {
    "id": 1,
    "code": "CTN",
    "name": "重庆至南京高铁沿线",
    "origin_city_name": "重庆",
    "destination_city_name": "南京",
    "total_distance_km": 1245,
    "is_active": true
  }
]
```

### 4.3 获取线路详情和城市节点

#### `GET /routes/{route_id}`

路径参数：

| 参数 | 类型 | 说明 |
|---|---|---|
| `route_id` | integer | 线路 ID |

响应 `data`：

```json
{
  "id": 1,
  "code": "CTN",
  "name": "重庆至南京高铁沿线",
  "origin_city_name": "重庆",
  "destination_city_name": "南京",
  "total_distance_km": 1245,
  "geometry": {
    "type": "LineString",
    "coordinates": [[106.5500, 29.6145], [108.3968, 30.7988], [109.4859, 30.2911], [111.3856, 30.6466], [112.2451, 30.3478], [114.4252, 30.6095], [117.3097, 31.7936], [118.7982, 31.9517]]
  },
  "stations": [
    {
      "city_id": 1,
      "city_name": "重庆",
      "station_name": "重庆北站",
      "station_order": 1,
      "distance_from_origin_km": 0.0,
      "longitude": 106.5500,
      "latitude": 29.6145
    }
  ]
}
```

`stations.longitude` 与 `stations.latitude` 是高德 GCJ-02 坐标系下的站点位置，和城市天气坐标分开维护。固定 8 个站点按顺序为重庆北、万州北、恩施、宜昌东、荆州、武汉、合肥南、南京南；`geometry` 按同一顺序生成。`geometry` 为空时，前端仍应使用 `stations` 绘制节点并展示页面，不应因地图路线缺失而阻塞天气功能。

### 4.4 获取城市基本信息

#### `GET /cities/{city_id}`

路径参数：`city_id`，城市 ID。

响应 `data`：

```json
{
  "id": 1,
  "name": "重庆",
  "city_code": "101040100",
  "province": "重庆市",
  "longitude": 106.5516,
  "latitude": 29.5630,
  "image_url": "/images/chongqing.jpg",
  "description": "山城与江城相依。",
  "climate_description": "夏季高温多雨，湿度较高。"
}
```

### 4.5 获取城市天气详情

#### `GET /cities/{city_id}/weather`

查询参数：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---:|---|---|
| `date` | string | 否 | 最新可用观测 | `YYYY-MM-DD`；传入后按日期精确查询 |

响应 `data`：

```json
{
  "city": {
    "id": 1,
    "name": "重庆",
    "longitude": 106.5516,
    "latitude": 29.5630
  },
  "date": "2026-07-30",
  "observed_at": "2026-07-30T08:00:00Z",
  "weather": {
    "temperature_c": 29.4,
    "feels_like_c": 33.1,
    "text": "多云",
    "code": 104,
    "humidity_percent": 78,
    "wind_speed_ms": 2.1,
    "wind_direction": "东南风",
    "precipitation_probability_percent": 35,
    "visibility_km": 8.0
  },
  "air_quality": {
    "aqi": 62,
    "pm25_ug_m3": 38.0,
    "pm10_ug_m3": 61.0,
    "primary_pollutant": "PM2.5"
  },
  "atmosphere": {
    "stability_class": "B-C",
    "stability_level": "不稳定至弱不稳定",
    "period": "day",
    "insolation_category": "moderate",
    "confidence": "estimated",
    "method": "pasquill-turner-estimate",
    "inputs": {
      "wind_speed_ms": 3.4,
      "cloud_cover_percent": 35,
      "solar_elevation_deg": 52.1
    },
    "explanation": "当前处于白天，中等日照、云量35%，风速3.4 m/s，近地层估算为不稳定至弱不稳定。",
    "calculation_version": "pasquill-v1"
  }
}
```

天气、空气质量或气象分析暂时不存在时，对应字段返回 `null`，整体接口仍可成功返回。稳定度使用帕斯奎尔方法近似判级，保留 `A-B`、`B-C`、`C-D` 过渡等级；由于数据源没有云底高度和风速观测高度，结果仅用于教学展示。城市诗句由前端图片注册表提供，不属于天气接口。

### 4.6 获取沿线气象剖面

#### `GET /routes/{route_id}/weather-profile`

用于 ECharts 绘制沿线变化图。

查询参数：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---:|---|---|
| `date` | string | 否 | 当前业务日期 | `YYYY-MM-DD` |
| `metrics` | string | 否 | 全部 | 逗号分隔：`temperature,humidity,aqi,wind_speed` |

响应 `data`：

```json
{
  "route_id": 1,
  "date": "2026-07-30",
  "distance_unit": "km",
  "points": [
    {
      "city_id": 1,
      "city_name": "重庆",
      "station_order": 1,
      "distance_from_origin_km": 0.0,
      "temperature_c": 29.4,
      "humidity_percent": 78,
      "aqi": 62,
      "wind_speed_ms": 2.1
    },
    {
      "city_id": 2,
      "city_name": "武汉",
      "station_order": 2,
      "distance_from_origin_km": 720.0,
      "temperature_c": 31.0,
      "humidity_percent": 65,
      "aqi": 48,
      "wind_speed_ms": 2.8
    }
  ],
  "missing_city_ids": []
}
```

`points` 必须按 `station_order` 升序返回。某城市没有数据时，该城市仍可出现在 `points` 中，对应指标为 `null`；`missing_city_ids` 用于前端提示数据缺失。
传入 `metrics` 时，每个点只返回所选指标对应的数值字段；城市、站序和里程字段始终返回。重复指标会自动去重，空值或未知指标返回 `422`。

### 4.7 管理员刷新天气

#### `POST /weather/refresh`

管理员立即从和风天气刷新所有启用线路的城市观测。请求不需要正文，但必须携带管理员 Bearer Token。接口不调用 DeepSeek，公网前端不调用此接口。已有自动或手动更新正在运行时返回 `40901`，天气服务未配置或不可用时返回 `50300`。

### 4.8 随机气象旅行

#### `GET /routes/{route_id}/random-trip`

随机返回线路中的一个城市，用于“开启一次气象旅行”。

查询参数：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---:|---|---|
| `date` | string | 否 | 当前业务日期 | 天气日期 |

响应 `data`：

```json
{
  "route_id": 1,
  "date": "2026-07-30",
  "station": {
    "city_id": 2,
    "city_name": "武汉",
    "station_name": "武汉站",
    "station_order": 2,
    "distance_from_origin_km": 720.0
  },
  "weather": {
    "temperature_c": 31.0,
    "feels_like_c": 35.0,
    "text": "晴",
    "humidity_percent": 65,
    "aqi": 48,
    "stability_level": "不稳定"
  }
}
```

随机数由后端生成。前端刷新页面或重复请求不应假设返回同一个城市。
所选日期没有该站观测时，`weather` 返回 `null`，站点信息仍正常返回。

### 4.9 获取或生成路线建议

#### `GET /routes/{route_id}/travel-advice`

返回该线路最近一次成功生成的建议。没有历史建议时返回 `data: null`，不会触发 AI。

#### `POST /routes/{route_id}/travel-advice`

管理员根据当天可用的沿线天气生成并保存一段 50–100 个汉字的路线建议。请求不需要正文，但必须携带管理员 Bearer Token；同一天再次成功生成时覆盖当天记录，生成失败时保留原记录。公网前端不调用此接口。

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "route_id": 1,
    "travel_date": "2026-07-30",
    "content": "沿线前段湿热且可能有雨，建议携带折叠伞并穿轻薄透气衣物；武汉至南京注意防晒补水，早晚温差变化时及时添衣。",
    "model_name": "deepseek-v4-flash",
    "generated_at": "2026-07-30T08:25:00Z",
    "is_stale": false
  },
  "request_id": "report-001"
}
```

路线不存在返回 `404`；当天没有任何可用观测返回 `409`；DeepSeek 未配置、超时或输出不合格返回 `503`。

### 4.10 内部每日更新

#### `GET /internal/daily-update`

只供 Vercel Cron 调用，必须携带 `CRON_SECRET` Bearer Token。请求先领取 PostgreSQL 更新租约和当日唯一执行记录，天气更新完成后再生成路线建议。重复触发当天已领取的任务不会重复消耗第三方 API。

| HTTP 状态 | 含义 |
|---:|---|
| `200` | 全部成功，或当天已有执行记录而跳过 |
| `207` | 部分城市或线路成功 |
| `409` | 另一自动或手动更新持有租约 |
| `500` | 天气和建议均未成功 |

该接口不在生产 OpenAPI 文档中公开，但 URL 本身不是安全边界，鉴权不可省略。

## 5. 外部 API 集成约定

外部 API 只由后端 `external/` 和 `services/` 调用，前端不能接触外部 API Key。外部返回值先转换为 CtoN 内部模型，再写入数据库或返回给前端。

### 5.1 和风天气 API

暂定用于天气和空气质量数据：

- 后端配置：`QWEATHER_API_KEY`、`QWEATHER_BASE_URL`；
- 通过 `cities.city_code` 查询城市；
- 获取当前天气、空气质量，以及稳定度判级所需的观测时间、风速和总云量；
- 统一转换为 `weather_observations` 和 `air_quality_observations`；
- 保存 `source = "qweather"` 和必要的 `raw_payload_json`；
- 请求超时建议 5 秒，失败时不覆盖数据库中已有有效数据。

和风 API 的字段名不直接暴露给前端。例如和风的天气描述应转换为 `weather.text`，温度应转换为 `temperature_c`。

太阳高度、日出和日落由后端根据城市经纬度及 `observed_at` 本地计算，不调用太阳辐射 API。白天按太阳高度划分日照等级，并在总云量超过 50% 时降低一级；全阴按中性 D 处理。夜间从日落前一小时持续到日出后一小时，按云量和风速查表。缺少风速、云量或有效时区时不生成稳定度记录。

### 5.2 高德地图 API

用于地图展示与固定站点坐标维护：

- `AMAP_WEB_SERVICE_KEY` 仅用于维护时以地点搜索/地理编码核验固定站点，不能进入前端；
- `AMAP_SECURITY_JS_CODE` 由后端 `/_AMapService/` 代理请求附加，不能进入前端；
- `VITE_AMAP_JS_KEY` 会在浏览器加载 SDK 时使用，必须限制允许域名；
- 前端只接收 GeoJSON 风格的 `geometry` 和站点节点，不在页面加载时调用地点搜索或路线规划；
- 固定高铁示范主线不用高德路线规划 API，因为其公交/驾车结果不代表高铁轨迹；
- 高德不可用时，前端仍可展示站点列表和天气数据。

如果使用高德地图 JavaScript SDK，浏览器端所需的安全配置只能使用受域名限制的前端 Key，不能把高权限 Web 服务 Key 写入 Vue 源码。

### 5.3 DeepSeek API

用于全线路旅行建议文本生成：

- 后端配置：`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`；
- 天气刷新接口本身不调用 DeepSeek；管理员手动触发建议接口或后端每日任务时才生成路线建议；
- 输入只使用已保存的当天路线天气快照，输出为 50–100 个汉字的单段建议，不合格时重试一次；
- 生成成功后写入 `travel_reports`，记录模型名、Prompt 哈希、生成时间和来源快照；
- AI 超时、失败或格式不合格不会影响天气更新，也不会覆盖上一次成功建议；
- 城市诗句按当前图片从前端静态注册表读取，不经过 API。

AI Prompt 不通过前端传入，避免用户覆盖系统约束或扩大生成内容范围。

## 6. 前后端交互约定

### 6.1 页面初始化

首页推荐请求顺序：

1. `GET /routes` 获取线路 ID；
2. `GET /routes/{route_id}` 获取节点和地图几何数据；
3. `GET /routes/{route_id}/weather-profile` 获取沿线图表数据；
4. 用户点击城市后调用 `GET /cities/{city_id}/weather`。

前端不应为每个城市重复请求线路详情。线路详情可以在页面状态中缓存。

### 6.2 城市详情

城市详情页以 `GET /cities/{city_id}/weather?date=YYYY-MM-DD` 为主要数据源。城市静态信息可与天气详情并行请求，或使用线路详情中已返回的城市字段。

### 6.3 加载、空数据和错误状态

- 请求开始时显示局部加载状态，不阻塞页面其他已完成区域；
- `data` 中某个对象为 `null` 时显示“暂无数据”，不能显示为 0；
- HTTP `404` 显示资源不存在；
- HTTP `422` 提示日期只支持最近 15 天；
- HTTP `502` 显示外部服务暂时不可用，并保留页面已有缓存数据；
- 网络错误允许用户点击重试，重试请求应复用原查询参数。

### 6.4 缓存和刷新

- 线路和城市静态信息可缓存 24 小时；
- 天气详情和剖面数据可缓存 10 分钟；
- 预设诗句随静态资源缓存；路线建议按日期保存在数据库中；
- 后端每日任务更新数据后，前端下次请求自然获得最新快照；
- 前端“刷新数据”并行调用天气、剖面和建议三个 GET，不触发任何外部 API 消耗；
- Vercel Cron 每天 UTC 22:00 触发；Hobby 在北京时间 06:00–06:59 的窗口内启动，不保证精确分钟；
- 自动任务失败后保留已有数据并记录执行结果，当天不自动重试；
- 前端不使用 `raw_payload_json`，也不根据外部 API 返回时间判断新旧。

### 6.5 幂等和并发

- 所有 GET 请求必须是幂等的；
- `POST /routes/{route_id}/travel-advice` 按 `(route_id, travel_date)` 覆盖当天建议；
- 后端使用数据库唯一约束防止同一天重复天气快照和报告；
- Cron、天气刷新和建议生成共用 PostgreSQL 过期租约；未取得租约时返回 `40901`，不得并发调用第三方服务；
- `daily_update_runs.run_date` 唯一，保证重复 Cron 请求不会重复调用第三方服务。

### 6.6 安全约定

- API Key、数据库连接信息和模型配置通过环境变量注入；
- 两个管理 POST 统一使用 `Authorization: Bearer <ADMIN_API_TOKEN>`，只供管理员使用；
- 不在响应中返回外部服务 Key、原始授权头或完整外部响应；
- 生产流量使用前端同源 rewrite 时 CORS 可为空；若配置则只接受 HTTPS 正式域名，并关闭交互文档和 OpenAPI JSON；
- 对 `route_id`、`city_id` 和日期参数使用 FastAPI/Pydantic 校验；
- 对路线建议请求进行限流，避免重复触发外部 AI 调用。

## 7. 推荐环境变量

```text
APP_ENV=development
APP_TIMEZONE=Asia/Shanghai
DATABASE_URL=postgresql://localhost/cton
DATABASE_MIGRATION_URL=postgresql://localhost/cton
TEST_DATABASE_URL=postgresql://localhost/cton_test
ADMIN_API_TOKEN=
CRON_SECRET=
CORS_ORIGINS=http://localhost:5173

QWEATHER_API_KEY=
QWEATHER_BASE_URL=

AMAP_WEB_SERVICE_KEY=
AMAP_SECURITY_JS_CODE=
AMAP_BASE_URL=https://restapi.amap.com

DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
```

前端 Project 单独配置 `BACKEND_ORIGIN` 与 `VITE_AMAP_JS_KEY`。`DATABASE_MIGRATION_URL` 只在本地初始化时使用，不保存到 Vercel Function 环境。

## 8. 接口实现建议

FastAPI 路由按业务拆分：

```text
backend/api/
├── health.py
├── route.py
├── city.py
├── weather.py
└── travel.py
```

外部服务适配放在：

```text
backend/external/
├── qweather_api.py
├── amap_api.py
└── deepseek_api.py
```

路由层只负责参数校验、状态码和响应模型；业务查询、数据更新和外部 API 调用放在 service 层；数据库模型不直接作为公共 API 响应模型，避免内部字段变化影响前端。
