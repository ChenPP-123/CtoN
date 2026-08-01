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
- 获取已生成的天气诗歌；
- 按日期生成并查询旅行气象报告。

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
| 温度直减率 | °C/km |
| 污染物浓度 | µg/m³ |

日期不传时，查询接口默认使用服务器当前 UTC 日期。当前动态数据只保留最近 15 个自然日，超出范围返回 `422`。

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
| 404 | `40401` | 资源不存在 |
| 409 | `40901` | 资源状态冲突 |
| 422 | `42201` | 日期超出 15 天数据范围 |
| 429 | `42901` | 请求过于频繁 |
| 502 | `50201` | 天气/地图/AI 外部服务失败 |
| 503 | `50301` | 后端服务暂时不可用 |
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
| `date` | string | 否 | 当前 UTC 日期 | `YYYY-MM-DD` |

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
    "stability_level": "弱不稳定",
    "lapse_rate_c_per_km": 8.2,
    "pressure_hpa": 985.0,
    "explanation": "午后地面加热增强，垂直混合作用增强。",
    "calculation_version": "v1"
  },
  "poem": {
    "content": "巴山云作幕，江风入夏城。",
    "model_name": "deepseek-chat",
    "generated_at": "2026-07-30T08:20:00Z"
  }
}
```

天气、空气质量、气象分析或诗歌暂时不存在时，对应字段返回 `null`，整体接口仍可成功返回。

### 4.6 获取沿线气象剖面

#### `GET /routes/{route_id}/weather-profile`

用于 ECharts 绘制沿线变化图。

查询参数：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---:|---|---|
| `date` | string | 否 | 当前 UTC 日期 | `YYYY-MM-DD` |
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

### 4.8 随机气象旅行

#### `GET /routes/{route_id}/random-trip`

随机返回线路中的一个城市，用于“开启一次气象旅行”。

查询参数：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---:|---|---|
| `date` | string | 否 | 当前 UTC 日期 | 天气日期 |

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
  },
  "poem": {
    "content": "晴光开汉水，南风过江城。"
  }
}
```

随机数由后端生成。前端刷新页面或重复请求不应假设返回同一个城市。

### 4.9 创建或获取旅行报告

#### `POST /travel-reports`

根据线路和出行日期生成报告。后端优先返回数据库中已有报告；没有报告时，使用沿线天气数据生成并保存。

请求体：

```json
{
  "route_id": 1,
  "travel_date": "2026-07-30"
}
```

字段：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `route_id` | integer | 是 | 线路 ID |
| `travel_date` | string | 是 | `YYYY-MM-DD`，必须在最近 15 天数据范围内 |

响应：首次生成可返回 `201 Created`，命中已有报告返回 `200 OK`。

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "id": 10,
    "route_id": 1,
    "travel_date": "2026-07-30",
    "title": "重庆至南京九小时气象旅行报告",
    "summary": "沿线由湿热多云转为晴热，再进入湿润降雨天气。",
    "recommendations": {
      "clothing": "沿线建议穿着轻薄透气衣物。",
      "umbrella": true,
      "heat_protection": "武汉段注意防晒和补水。"
    },
    "cities": [
      {
        "city_id": 1,
        "city_name": "重庆",
        "temperature_c": 29.4,
        "weather_text": "多云",
        "clothing": "轻薄透气衣物",
        "umbrella": true
      }
    ],
    "generated_at": "2026-07-30T08:25:00Z"
  },
  "request_id": "report-001"
}
```

#### `GET /travel-reports/{report_id}`

查询已生成的报告，路径参数为 `report_id`。返回结构与创建接口的 `data` 相同。

#### `GET /routes/{route_id}/travel-report`

按线路和日期查询报告。查询参数 `date` 必填，格式为 `YYYY-MM-DD`。报告不存在时返回 `404`，不会在 GET 请求中触发 AI 生成。

## 5. 外部 API 集成约定

外部 API 只由后端 `external/` 和 `services/` 调用，前端不能接触外部 API Key。外部返回值先转换为 CtoN 内部模型，再写入数据库或返回给前端。

### 5.1 和风天气 API

暂定用于天气和空气质量数据：

- 后端配置：`QWEATHER_API_KEY`、`QWEATHER_BASE_URL`；
- 通过 `cities.city_code` 查询城市；
- 获取当前天气、空气质量和预报所需字段；
- 统一转换为 `weather_observations` 和 `air_quality_observations`；
- 保存 `source = "qweather"` 和必要的 `raw_payload_json`；
- 请求超时建议 5 秒，失败时不覆盖数据库中已有有效数据。

和风 API 的字段名不直接暴露给前端。例如和风的天气描述应转换为 `weather.text`，温度应转换为 `temperature_c`。

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

暂定用于天气诗歌和旅行建议文本生成：

- 后端配置：`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`；
- 诗歌生成输入必须来自已保存的天气快照、城市文化和气候信息；
- 点击“更新观测”时，后端先完成所有城市天气获取，再为本次天气更新成功的城市生成诗歌；
- 诗歌为两句或四句中文绝句，同一首诗统一为五言或七言；服务端校验格式，不合格时重试一次；
- 成功后写入 `poems`，记录模型名、Prompt 哈希和生成时间；
- 旅行报告生成成功后写入 `travel_reports`；
- 单城 AI 超时、失败或格式不合格不会使天气刷新失败；该城市不保存半成品，前端在天气详情中收到 `poem: null`。

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
- 诗歌和旅行报告在日期不变时可缓存 24 小时；
- 后端每日任务更新数据后，前端下次请求自然获得最新快照；
- 前端不使用 `raw_payload_json`，也不根据外部 API 返回时间判断新旧。

### 6.5 幂等和并发

- 所有 GET 请求必须是幂等的；
- `POST /travel-reports` 按 `(route_id, travel_date)` 幂等，重复提交返回同一份报告；
- 后端使用数据库唯一约束防止同一天重复天气快照和报告；
- 同一报告正在生成时，后续请求应等待已有任务或返回 `40901`，不得并发调用多个 AI 请求。

### 6.6 安全约定

- API Key、数据库连接信息和模型配置通过环境变量注入；
- 不在响应中返回外部服务 Key、原始授权头或完整外部响应；
- 生产环境配置 CORS 白名单，只允许 CtoN 前端域名；
- 对 `route_id`、`city_id` 和日期参数使用 FastAPI/Pydantic 校验；
- 对旅行报告请求进行限流，避免重复触发外部 AI 调用。

## 7. 推荐环境变量

```text
APP_ENV=development
DATABASE_URL=sqlite:///./data/cton.db

QWEATHER_API_KEY=
QWEATHER_BASE_URL=

AMAP_WEB_SERVICE_KEY=
AMAP_SECURITY_JS_CODE=
VITE_AMAP_JS_KEY=
AMAP_BASE_URL=https://restapi.amap.com

DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

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
