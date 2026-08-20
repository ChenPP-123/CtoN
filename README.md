# CtoN

重庆至南京高铁沿线的气象可视化网站。前端展示地图、城市天气、沿线剖面、随机旅途和预设诗句；后端从和风天气更新观测，并使用 DeepSeek 生成全线路旅途建议。

## 生产架构

同一仓库部署为两个 Vercel Project：

- 后端 Project 的 Root Directory 为仓库根目录。FastAPI 作为单个 Python 3.13 Function 运行在新加坡 `sin1`，数据保存在 Neon PostgreSQL 新加坡区。
- 前端 Project 的 Root Directory 为 `frontend`。浏览器只请求相对路径 `/api/v1` 和 `/_AMapService`，Vercel 将它们同源转发到后端 Project。

后端不在冷启动时建表、写种子或启动后台线程。Vercel Cron 每天 UTC 22:00 触发内部更新接口，即北京时间 06:00–06:59 的 Hobby 执行窗口；Hobby 不保证精确到某一分钟。天气先更新，随后按线路生成建议，结果写入 `daily_update_runs`。

## 配置

后端从仓库根目录 `.env` 读取本地配置；前端只从 `frontend/.env` 读取构建配置。分别复制示例：

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
```

生产运行时必须配置：

```dotenv
APP_ENV=production
APP_TIMEZONE=Asia/Shanghai
DATABASE_URL=postgresql://...-pooler.../cton?sslmode=require
ADMIN_API_TOKEN=
CRON_SECRET=
CORS_ORIGINS=
QWEATHER_API_KEY=
QWEATHER_BASE_URL=
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
AMAP_SECURITY_JS_CODE=
```

前端生产变量：

```dotenv
BACKEND_ORIGIN=https://your-backend-project.vercel.app
VITE_AMAP_JS_KEY=
```

`ADMIN_API_TOKEN` 和 `CRON_SECRET` 必须互不相同且至少 32 个字符。生产流量经同源 rewrite 时 `CORS_ORIGINS` 可为空；若配置，只接受 HTTPS 正式域名。`DATABASE_MIGRATION_URL` 仅供本地初始化使用，不应保存到 Vercel Function 环境。`AMAP_WEB_SERVICE_KEY` 仅为可选维护配置。

## 数据库初始化

先用 Neon 非池化直连地址显式建表并写入固定线路配置：

```bash
source .venv/bin/activate
DATABASE_MIGRATION_URL='postgresql://...' python -m backend.database
```

命令可重复执行，只更新固定线路、城市和站点配置，不覆盖真实天气或旅行建议。当前没有 SQLite 生产数据迁移路径；旧本地数据库直接废弃。

## 本地运行

准备 PostgreSQL 17、Python 3.13 和 Node.js 22，然后：

```bash
source .venv/bin/activate
pip install -r requirements.txt
python -m backend.database
uvicorn backend.main:app --reload
```

另一个终端启动前端：

```bash
cd frontend
npm ci
npm run dev
```

Vite 会将 `/api` 和 `/_AMapService` 代理到 `http://localhost:8000`。地图 JS Key 必须限制允许域名；高德安全密钥只保存在后端并由代理注入。

## 管理接口

公网前端只调用 GET。管理员可从可信终端手动触发：

```bash
curl -X POST https://backend.example/api/v1/weather/refresh \
  -H "Authorization: Bearer ${ADMIN_API_TOKEN}"
curl -X POST https://backend.example/api/v1/routes/1/travel-advice \
  -H "Authorization: Bearer ${ADMIN_API_TOKEN}"
```

Cron 使用独立的 `GET /api/v1/internal/daily-update` 和 `CRON_SECRET`。所有第三方更新共用 PostgreSQL 过期租约；并发手动更新返回业务码 `40901`，函数异常退出后租约会自动过期。

## 验证

测试数据库名必须以 `_test` 结尾：

```bash
source .venv/bin/activate
TEST_DATABASE_URL=postgresql:///cton_test pytest -q
pip check

cd frontend
npm test
BACKEND_ORIGIN=https://backend.example npm run build
npm audit --omit=dev --audit-level=high
```

完整部署、恢复演练和上线验收见 [Vercel 部署手册](docs/Production_Deployment.md)。生产恢复依赖 Neon 当前套餐提供的恢复窗口，不再使用 ECS、Nginx、systemd、SQLite 备份或阿里云 OSS。
