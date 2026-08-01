# CtoN 数据库设计文档

版本：1.0  
项目：CtoN（Chongqing to Nanjing）  
数据库：SQLite 3  
ORM：SQLAlchemy

## 1. 设计目标

数据库服务于“重庆至南京高铁沿线气象可视化系统”，支持：

- 展示线路、城市节点及高铁距离；
- 查询某个城市某一天的天气、空气质量和气象分析；
- 生成沿线温度、湿度、AQI、风速剖面；
- 保存按天气生成的两句诗；
- 根据出行日期保存一份旅行气象报告。

设计原则：静态地理信息与动态气象快照分离；同一城市同一日期只保留一条业务快照；动态数据只保留最近半个月（15 个自然日）；所有外部数据均保存来源和更新时间，便于排错和重新生成。

## 2. 数据库约定

### 2.1 SQLite 设置

应用启动时执行：

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
```

SQLite 没有独立的 `BOOLEAN`、`DATE`、`DATETIME` 类型，因此使用以下约定：

| 逻辑类型 | SQLite 类型 | 约定 |
|---|---|---|
| 主键 | `INTEGER` | `INTEGER PRIMARY KEY`，由 SQLite 生成；不使用 UUID |
| 短文本 | `TEXT` | UTF-8，名称、状态、描述等 |
| 整数 | `INTEGER` | 计数、排序、分钟、百分比等 |
| 小数 | `REAL` | 温度、经纬度、气压、距离等 |
| 布尔值 | `INTEGER` | 仅允许 `0` 或 `1` |
| 日期 | `TEXT` | ISO 8601 日期：`YYYY-MM-DD` |
| 时间 | `TEXT` | UTC ISO 8601：`YYYY-MM-DDTHH:MM:SSZ` |
| JSON | `TEXT` | 合法 JSON 字符串；仅用于外部原始响应或结构化报告 |

所有距离单位为 km，温度为 °C，湿度和降水概率为 %，风速为 m/s，能见度为 km，气压为 hPa，温度直减率为 °C/km，污染物浓度为 µg/m³。

## 3. ER 设计

```mermaid
erDiagram
    routes ||--o{ route_stations : contains
    cities ||--o{ route_stations : appears_on
    cities ||--o{ weather_observations : has
    cities ||--o{ air_quality_observations : has
    cities ||--o{ atmosphere_analyses : has
    cities ||--o{ poems : inspires
    weather_observations ||--o| air_quality_observations : reports
    weather_observations ||--o| atmosphere_analyses : analyzed_as
    weather_observations ||--o{ poems : generates
    routes ||--o{ travel_reports : used_by

    routes {
        INTEGER id PK
        TEXT code UK
        TEXT name
        TEXT origin_city_name
        TEXT destination_city_name
        INTEGER total_distance_km
        TEXT geometry_json
        INTEGER is_active
    }
    cities {
        INTEGER id PK
        TEXT name UK
        TEXT city_code UK
        TEXT province
        REAL longitude
        REAL latitude
        TEXT image_url
        TEXT description
        TEXT climate_description
    }
    route_stations {
        INTEGER id PK
        INTEGER route_id FK
        INTEGER city_id FK
        INTEGER station_order
        REAL distance_from_origin_km
        TEXT station_name
        REAL longitude
        REAL latitude
    }
    weather_observations {
        INTEGER id PK
        INTEGER city_id FK
        TEXT observation_date
        TEXT observed_at
        REAL temperature_c
        REAL feels_like_c
        TEXT weather_text
        INTEGER weather_code
        INTEGER humidity_percent
        REAL wind_speed_ms
        TEXT wind_direction
        INTEGER precipitation_probability_percent
        REAL visibility_km
        TEXT source
    }
    air_quality_observations {
        INTEGER id PK
        INTEGER weather_observation_id FK
        INTEGER city_id FK
        INTEGER aqi
        REAL pm25_ug_m3
        REAL pm10_ug_m3
        TEXT primary_pollutant
    }
    atmosphere_analyses {
        INTEGER id PK
        INTEGER weather_observation_id FK
        INTEGER city_id FK
        TEXT stability_level
        REAL lapse_rate_c_per_km
        REAL pressure_hpa
        TEXT explanation
        TEXT calculation_version
    }
    poems {
        INTEGER id PK
        INTEGER city_id FK
        INTEGER weather_observation_id FK
        TEXT poem_date
        TEXT content
        TEXT model_name
        TEXT prompt_hash
        TEXT generated_at
    }
    travel_reports {
        INTEGER id PK
        INTEGER route_id FK
        TEXT travel_date
        TEXT title
        TEXT summary
        TEXT report_json
        TEXT generated_at
    }
```

关系说明：

1. `routes` 与 `cities` 是多对多关系，由 `route_stations` 保存线路顺序和距起点距离；这样同一城市可以出现在多条线路中。
2. `weather_observations` 是城市天气快照主表，`air_quality_observations` 和 `atmosphere_analyses` 为其一对一扩展记录。
3. `poems` 关联具体天气快照，避免诗歌与后来更新的天气数据失去对应关系。
4. `travel_reports` 保存已生成的旅行报告快照，不在用户每次访问时重新调用 AI。

## 4. 表结构

### 4.1 `routes`：高铁线路

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `INTEGER` | PK | 线路 ID |
| `code` | `TEXT` | NOT NULL, UNIQUE | 稳定业务编码，如 `CTN` |
| `name` | `TEXT` | NOT NULL | 线路名称 |
| `origin_city_name` | `TEXT` | NOT NULL | 起点城市显示名 |
| `destination_city_name` | `TEXT` | NOT NULL | 终点城市显示名 |
| `total_distance_km` | `INTEGER` | NOT NULL, CHECK >= 0 | 线路总距离 |
| `geometry_json` | `TEXT` | NULL | 高德地图路线坐标 JSON；不参与业务查询 |
| `is_active` | `INTEGER` | NOT NULL, DEFAULT 1, CHECK IN (0,1) | 是否在前端展示 |
| `created_at` | `TEXT` | NOT NULL | 创建时间 |
| `updated_at` | `TEXT` | NOT NULL | 修改时间 |

### 4.2 `cities`：城市静态信息

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `INTEGER` | PK | 城市 ID |
| `name` | `TEXT` | NOT NULL, UNIQUE | 城市名称 |
| `city_code` | `TEXT` | NOT NULL, UNIQUE | 天气 API 城市编码 |
| `province` | `TEXT` | NOT NULL | 所属省级行政区 |
| `longitude` | `REAL` | NOT NULL, CHECK BETWEEN -180 AND 180 | 经度 |
| `latitude` | `REAL` | NOT NULL, CHECK BETWEEN -90 AND 90 | 纬度 |
| `image_url` | `TEXT` | NULL | 静态城市图片路径或 URL |
| `description` | `TEXT` | NULL | 城市简介 |
| `climate_description` | `TEXT` | NULL | 气候特点 |
| `created_at` | `TEXT` | NOT NULL | 创建时间 |
| `updated_at` | `TEXT` | NOT NULL | 修改时间 |

### 4.3 `route_stations`：线路城市节点

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `INTEGER` | PK | 节点 ID |
| `route_id` | `INTEGER` | NOT NULL, FK `routes.id` ON DELETE CASCADE | 所属线路 |
| `city_id` | `INTEGER` | NOT NULL, FK `cities.id` RESTRICT | 城市 |
| `station_order` | `INTEGER` | NOT NULL, CHECK >= 1 | 沿线顺序，从 1 开始 |
| `distance_from_origin_km` | `REAL` | NOT NULL, CHECK >= 0 | 距起点距离 |
| `station_name` | `TEXT` | NOT NULL | 对应车站名称 |
| `longitude` | `REAL` | NOT NULL | 高德 GCJ-02 站点经度，与城市天气坐标分离 |
| `latitude` | `REAL` | NOT NULL | 高德 GCJ-02 站点纬度，与城市天气坐标分离 |

唯一约束：`(route_id, city_id)`、`(route_id, station_order)`。

### 4.4 `weather_observations`：天气快照

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `INTEGER` | PK | 天气快照 ID |
| `city_id` | `INTEGER` | NOT NULL, FK `cities.id` RESTRICT | 城市 |
| `observation_date` | `TEXT` | NOT NULL | 业务日期 |
| `observed_at` | `TEXT` | NOT NULL | API 数据观测/更新时间 |
| `temperature_c` | `REAL` | NOT NULL | 当前温度 |
| `feels_like_c` | `REAL` | NULL | 体感温度 |
| `weather_text` | `TEXT` | NOT NULL | 天气描述 |
| `weather_code` | `INTEGER` | NULL | API 天气代码 |
| `humidity_percent` | `INTEGER` | NOT NULL, CHECK BETWEEN 0 AND 100 | 相对湿度 |
| `wind_speed_ms` | `REAL` | NULL, CHECK >= 0 | 风速 |
| `wind_direction` | `TEXT` | NULL | 风向，如东北风 |
| `precipitation_probability_percent` | `INTEGER` | NULL, CHECK BETWEEN 0 AND 100 | 降水概率 |
| `visibility_km` | `REAL` | NULL, CHECK >= 0 | 能见度 |
| `source` | `TEXT` | NOT NULL | 数据源，如 `qweather` |
| `raw_payload_json` | `TEXT` | NULL | 原始 API 响应，便于审计 |
| `created_at` | `TEXT` | NOT NULL | 入库时间 |

唯一约束：`(city_id, observation_date)`。每日更新采用 UPSERT，保证同一城市每天只有当前快照。

### 4.5 `air_quality_observations`：空气质量

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `INTEGER` | PK | 空气质量记录 ID |
| `weather_observation_id` | `INTEGER` | NOT NULL, UNIQUE, FK `weather_observations.id` CASCADE | 对应天气快照 |
| `city_id` | `INTEGER` | NOT NULL, FK `cities.id` RESTRICT | 冗余城市 ID，便于按城市查询 |
| `aqi` | `INTEGER` | NOT NULL, CHECK >= 0 | 空气质量指数 |
| `pm25_ug_m3` | `REAL` | NULL, CHECK >= 0 | PM2.5 |
| `pm10_ug_m3` | `REAL` | NULL, CHECK >= 0 | PM10 |
| `primary_pollutant` | `TEXT` | NULL | 首要污染物 |
| `created_at` | `TEXT` | NOT NULL | 入库时间 |

### 4.6 `atmosphere_analyses`：大气稳定度分析

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `INTEGER` | PK | 分析记录 ID |
| `weather_observation_id` | `INTEGER` | NOT NULL, UNIQUE, FK `weather_observations.id` CASCADE | 对应天气快照 |
| `city_id` | `INTEGER` | NOT NULL, FK `cities.id` RESTRICT | 城市 |
| `stability_level` | `TEXT` | NOT NULL | 稳定度，如稳定、弱不稳定、不稳定 |
| `lapse_rate_c_per_km` | `REAL` | NOT NULL | 温度直减率 |
| `pressure_hpa` | `REAL` | NULL, CHECK > 0 | 地面气压 |
| `explanation` | `TEXT` | NOT NULL | 面向用户的气象解释 |
| `calculation_version` | `TEXT` | NOT NULL | 计算规则版本 |
| `created_at` | `TEXT` | NOT NULL | 计算时间 |

### 4.7 `poems`：天气诗歌

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `INTEGER` | PK | 诗歌 ID |
| `city_id` | `INTEGER` | NOT NULL, FK `cities.id` RESTRICT | 城市 |
| `weather_observation_id` | `INTEGER` | NOT NULL, FK `weather_observations.id` RESTRICT | 生成时使用的天气 |
| `content` | `TEXT` | NOT NULL | 两句或四句五言、七言绝句正文 |
| `model_name` | `TEXT` | NOT NULL | AI 模型名称，如 `deepseek-chat` |
| `prompt_hash` | `TEXT` | NULL | Prompt 哈希，用于去重和审计 |
| `generated_at` | `TEXT` | NOT NULL | 生成时间 |

唯一约束：`weather_observation_id`。同一条当前天气快照只保留一首诗歌；重新生成时覆盖该快照的诗歌内容。

### 4.8 `travel_reports`：旅行气象报告

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `INTEGER` | PK | 报告 ID |
| `route_id` | `INTEGER` | NOT NULL, FK `routes.id` RESTRICT | 使用的线路 |
| `travel_date` | `TEXT` | NOT NULL | 出行日期 |
| `title` | `TEXT` | NOT NULL | 报告标题 |
| `summary` | `TEXT` | NOT NULL | 页面摘要 |
| `report_json` | `TEXT` | NOT NULL | 各城市天气、穿衣/雨具/防暑建议等 JSON |
| `generated_at` | `TEXT` | NOT NULL | 生成时间 |
| `source_snapshot_json` | `TEXT` | NULL | 生成时使用的天气记录 ID 列表 |

唯一约束：`(route_id, travel_date)`，同一线路同一天复用已生成报告。

## 5. 约束与数据一致性

- 删除城市前必须先移除其线路节点和气象数据；生产环境建议禁止删除，改为业务层归档。
- `air_quality_observations.city_id` 和对应天气记录的 `city_id` 必须相同；SQLAlchemy 写入时由服务层校验。
- `atmosphere_analyses` 的输入是天气快照，计算规则变化时更新 `calculation_version` 并重新计算。
- 外部 API 失败时不覆盖已有有效快照；任务失败应由调度器记录日志并重试。
- `raw_payload_json`、`report_json`、`geometry_json` 写入前必须通过 JSON 序列化，读取后必须校验结构。
- 当前设计只保存每日快照。如果将来需要小时级曲线，应新增小时观测表，不改变每日查询接口的数据含义。

### 5.1 数据保留策略

- `weather_observations`、`air_quality_observations`、`atmosphere_analyses`、`poems` 和 `travel_reports` 只保留最近 15 个自然日的数据，包含当天，即 `今天` 以及之前 14 天。
- `routes`、`cities`、`route_stations` 属于线路和城市静态配置，不受此清理策略影响。
- 每日数据更新成功后执行一次清理任务；清理任务失败不能影响当天数据写入，应记录错误并在下一次调度时重试。
- 清理以 UTC 日期为准，与文档中日期字段的时间约定保持一致。

清理动态数据时先删除依赖天气快照的诗歌，再删除天气快照；空气质量和大气分析会因外键 `ON DELETE CASCADE` 自动删除。旅行报告按自身出行日期单独清理：

```sql
BEGIN;

DELETE FROM poems
WHERE poem_date < date('now', '-14 days');

DELETE FROM travel_reports
WHERE travel_date < date('now', '-14 days');

DELETE FROM weather_observations
WHERE observation_date < date('now', '-14 days');

COMMIT;
```

生产环境应在执行清理前确认 `PRAGMA foreign_keys = ON`。若任务中途失败，应执行 `ROLLBACK`，不要提交部分清理结果。

## 6. 索引设计

SQLite 会自动为主键和 UNIQUE 约束建立索引，以下索引用于主要页面查询：

```sql
CREATE INDEX idx_route_stations_route_order
    ON route_stations(route_id, station_order);

CREATE INDEX idx_route_stations_city
    ON route_stations(city_id);

CREATE INDEX idx_weather_city_date
    ON weather_observations(city_id, observation_date DESC);

CREATE INDEX idx_weather_date
    ON weather_observations(observation_date);

CREATE INDEX idx_air_quality_city
    ON air_quality_observations(city_id);

CREATE INDEX idx_atmosphere_city
    ON atmosphere_analyses(city_id);

CREATE INDEX idx_poems_city_date
    ON poems(city_id, poem_date DESC);

CREATE INDEX idx_travel_reports_route_date
    ON travel_reports(route_id, travel_date DESC);
```

索引取舍：不为每个数值字段建立索引，因为温度、AQI 等主要用于沿线结果返回后的图表计算，而不是单字段过滤；索引过多会增加每日 UPSERT 成本和数据库文件体积。

## 7. 建表示例

以下 DDL 展示关键约束，实际项目可由 SQLAlchemy migration 生成：

```sql
CREATE TABLE routes (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    origin_city_name TEXT NOT NULL,
    destination_city_name TEXT NOT NULL,
    total_distance_km INTEGER NOT NULL CHECK (total_distance_km >= 0),
    geometry_json TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE cities (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    city_code TEXT NOT NULL UNIQUE,
    province TEXT NOT NULL,
    longitude REAL NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    latitude REAL NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    image_url TEXT,
    description TEXT,
    climate_description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE route_stations (
    id INTEGER PRIMARY KEY,
    route_id INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
    city_id INTEGER NOT NULL REFERENCES cities(id) ON DELETE RESTRICT,
    station_order INTEGER NOT NULL CHECK (station_order >= 1),
    distance_from_origin_km REAL NOT NULL CHECK (distance_from_origin_km >= 0),
    station_name TEXT NOT NULL,
    UNIQUE (route_id, city_id),
    UNIQUE (route_id, station_order)
);

CREATE TABLE weather_observations (
    id INTEGER PRIMARY KEY,
    city_id INTEGER NOT NULL REFERENCES cities(id) ON DELETE RESTRICT,
    observation_date TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    temperature_c REAL NOT NULL,
    feels_like_c REAL,
    weather_text TEXT NOT NULL,
    weather_code INTEGER,
    humidity_percent INTEGER NOT NULL CHECK (humidity_percent BETWEEN 0 AND 100),
    wind_speed_ms REAL CHECK (wind_speed_ms >= 0),
    wind_direction TEXT,
    precipitation_probability_percent INTEGER CHECK (precipitation_probability_percent BETWEEN 0 AND 100),
    visibility_km REAL CHECK (visibility_km >= 0),
    source TEXT NOT NULL,
    raw_payload_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (city_id, observation_date)
);
```

其余五张表按第 4 节字段定义创建，并分别建立第 6 节索引。创建所有表后再执行 `PRAGMA foreign_keys = ON` 的连接初始化代码。

## 8. 示例数据

示例日期统一使用 `2026-07-30`，时间使用 UTC；数值仅用于开发和接口联调，不代表真实天气。

```sql
INSERT INTO routes
    (id, code, name, origin_city_name, destination_city_name,
     total_distance_km, is_active, created_at, updated_at)
VALUES
    (1, 'CTN', '重庆至南京高铁沿线', '重庆', '南京', 1200, 1,
     '2026-07-29T16:00:00Z', '2026-07-29T16:00:00Z');

INSERT INTO cities
    (id, name, city_code, province, longitude, latitude,
     image_url, description, climate_description, created_at, updated_at)
VALUES
    (1, '重庆', '101040100', '重庆市', 106.5516, 29.5630,
     '/images/chongqing.jpg', '山城与江城相依。', '夏季高温多雨，湿度较高。',
     '2026-07-29T16:00:00Z', '2026-07-29T16:00:00Z'),
    (2, '武汉', '101200101', '湖北省', 114.3054, 30.5931,
     '/images/wuhan.jpg', '江城，长江与汉江交汇。', '夏季炎热，降水集中。',
     '2026-07-29T16:00:00Z', '2026-07-29T16:00:00Z'),
    (3, '南京', '101190101', '江苏省', 118.7969, 32.0603,
     '/images/nanjing.jpg', '历史文化名城。', '夏季高温湿润，梅雨期降水明显。',
     '2026-07-29T16:00:00Z', '2026-07-29T16:00:00Z');

INSERT INTO route_stations
    (route_id, city_id, station_order, distance_from_origin_km, station_name)
VALUES
    (1, 1, 1, 0.0, '重庆北站'),
    (1, 2, 2, 720.0, '武汉站'),
    (1, 3, 3, 1200.0, '南京南站');

INSERT INTO weather_observations
    (id, city_id, observation_date, observed_at, temperature_c, feels_like_c,
     weather_text, weather_code, humidity_percent, wind_speed_ms, wind_direction,
     precipitation_probability_percent, visibility_km, source, created_at)
VALUES
    (1001, 1, '2026-07-30', '2026-07-30T08:00:00Z', 29.4, 33.1, '多云', 104, 78, 2.1, '东南风', 35, 8.0, 'qweather', '2026-07-30T08:05:00Z'),
    (1002, 2, '2026-07-30', '2026-07-30T08:00:00Z', 31.0, 35.0, '晴', 100, 65, 2.8, '南风', 15, 12.0, 'qweather', '2026-07-30T08:05:00Z'),
    (1003, 3, '2026-07-30', '2026-07-30T08:00:00Z', 30.2, 34.2, '小雨', 305, 82, 1.9, '东风', 70, 6.0, 'qweather', '2026-07-30T08:05:00Z');

INSERT INTO air_quality_observations
    (weather_observation_id, city_id, aqi, pm25_ug_m3, pm10_ug_m3, primary_pollutant, created_at)
VALUES
    (1001, 1, 62, 38.0, 61.0, 'PM2.5', '2026-07-30T08:06:00Z'),
    (1002, 2, 48, 24.0, 45.0, NULL, '2026-07-30T08:06:00Z'),
    (1003, 3, 55, 31.0, 52.0, 'PM2.5', '2026-07-30T08:06:00Z');

INSERT INTO atmosphere_analyses
    (weather_observation_id, city_id, stability_level, lapse_rate_c_per_km,
     pressure_hpa, explanation, calculation_version, created_at)
VALUES
    (1001, 1, '弱不稳定', 8.2, 985.0, '午后地面加热增强，垂直混合作用增强。', 'v1', '2026-07-30T08:10:00Z'),
    (1002, 2, '不稳定', 9.5, 1002.0, '地面升温明显，有利于近地层空气交换。', 'v1', '2026-07-30T08:10:00Z'),
    (1003, 3, '中性', 6.1, 1008.0, '云雨天气削弱地面加热，垂直混合处于中等水平。', 'v1', '2026-07-30T08:10:00Z');

INSERT INTO poems
    (city_id, weather_observation_id, poem_date, content, model_name, prompt_hash, generated_at)
VALUES
    (1, 1001, '2026-07-30', '巴山云作幕，江风入夏城。', 'deepseek-chat', 'sha256:example-cq', '2026-07-30T08:20:00Z'),
    (2, 1002, '2026-07-30', '晴光开汉水，南风过江城。', 'deepseek-chat', 'sha256:example-wh', '2026-07-30T08:20:00Z'),
    (3, 1003, '2026-07-30', '梧桐听细雨，钟山入暮云。', 'deepseek-chat', 'sha256:example-nj', '2026-07-30T08:20:00Z');

INSERT INTO travel_reports
    (route_id, travel_date, title, summary, report_json, generated_at, source_snapshot_json)
VALUES
    (1, '2026-07-30', '重庆至南京九小时气象旅行报告',
     '沿线由湿热多云转为晴热，再进入湿润降雨天气。',
     '{"cities":[{"city_id":1,"clothing":"轻薄透气衣物","umbrella":true},{"city_id":2,"clothing":"短袖并注意防晒","umbrella":false},{"city_id":3,"clothing":"短袖，建议携带雨具","umbrella":true}]}',
     '2026-07-30T08:25:00Z', '[1001,1002,1003]');
```

## 9. 常用查询

### 9.1 查询线路沿线最新天气

```sql
SELECT rs.station_order, rs.distance_from_origin_km, c.name,
       w.temperature_c, w.humidity_percent, w.weather_text,
       aq.aqi, aa.stability_level
FROM route_stations rs
JOIN cities c ON c.id = rs.city_id
LEFT JOIN weather_observations w
  ON w.city_id = c.id AND w.observation_date = '2026-07-30'
LEFT JOIN air_quality_observations aq ON aq.weather_observation_id = w.id
LEFT JOIN atmosphere_analyses aa ON aa.weather_observation_id = w.id
WHERE rs.route_id = 1
ORDER BY rs.station_order;
```

### 9.2 生成气象剖面数据

沿线图表使用 `route_stations.distance_from_origin_km` 作为横轴，并按 `station_order` 排序；温度、湿度、AQI、风速分别来自天气和空气质量表。这样图表不依赖城市名称排序，也不会把城市间距误认为等距。

## 10. 更新流程与事务边界

每日任务按以下顺序执行：

1. 查询启用线路及其城市节点。
2. 对每个城市调用天气 API，在一个事务中 UPSERT `weather_observations`。
3. 使用同一 `weather_observation_id` UPSERT 空气质量和大气分析。
4. 仅当当前天气快照变化且不存在诗歌时调用 DeepSeek，成功后插入 `poems`。
5. 根据本次快照生成并 UPSERT `travel_reports`。
6. 提交当天数据后执行 15 个自然日之外的动态数据清理。

每个城市的天气相关写入使用独立事务，避免单个 API 失败回滚全部城市；诗歌和报告生成属于外部调用，调用成功后才写入数据库。外部调用不应持有数据库事务。

## 11. 备份与维护

- SQLite 文件应放在后端数据目录，不放在前端静态目录。
- 部署时使用 SQLite 在线备份或应用停机备份，不直接复制正在写入的数据库文件。
- 定期执行 `PRAGMA integrity_check;`。
- WAL 文件和数据库文件必须一起纳入备份策略。
- 生产环境保留每日数据库备份，至少保留最近 15 天；备份保留期不应短于动态数据保留期。
