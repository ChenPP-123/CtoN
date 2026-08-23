# CtoN Vercel Hobby 部署手册

本文对应一个个人 Git 仓库、两个 Vercel Project 和一个 Neon PostgreSQL 新加坡数据库。前端与后端全天可访问；定时更新受 Vercel Hobby Cron 调度精度限制。

## 1. 准备

- GitHub、GitLab 或 Bitbucket 的个人仓库。Vercel Hobby 不支持连接组织拥有的私有仓库。
- Vercel Hobby 账号和 Vercel CLI。
- 通过 Vercel Marketplace 创建的 Neon，区域选择 AWS Singapore。
- 和风天气、DeepSeek、高德地图凭据。
- 本地 Python 3.13、PostgreSQL 17、Node.js 22。

```bash
brew install postgresql@17 webp
# 使用 fnm 或 nvm 安装 Node.js 22
npm install -g vercel@latest
vercel --version
```

## 2. 创建后端 Project

1. 在 Vercel 导入仓库，Root Directory 保持仓库根目录。
2. `vercel.json` 将 Framework Preset 明确固定为 FastAPI。
3. `pyproject.toml` 将入口固定为 `backend.main:app`，`.python-version` 固定 3.13。
4. `vercel.json` 将函数区域设为 `sin1`，并注册 `0 22 * * *` Cron。FastAPI 默认使用 Fluid Compute，Hobby 的默认最长执行时间为 300 秒。

后端生产变量：

```dotenv
APP_ENV=production
APP_TIMEZONE=Asia/Shanghai
DATABASE_URL=postgresql://...-pooler.../cton?sslmode=require
ADMIN_API_TOKEN=<至少32字符>
CRON_SECRET=<至少32字符且不同于管理员令牌>
CORS_ORIGINS=
QWEATHER_API_KEY=
QWEATHER_BASE_URL=
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
AMAP_SECURITY_JS_CODE=
```

Neon 应提供两个地址：

- `DATABASE_URL` 使用带 `-pooler` 的池化地址，保存到后端 Vercel Project。
- `DATABASE_MIGRATION_URL` 使用非池化直连地址，只在本地初始化时临时使用。

生成两个令牌：

```bash
openssl rand -hex 32
openssl rand -hex 32
```

生产配置缺少数据库、管理员令牌、Cron 密钥、和风天气、DeepSeek 或高德安全密钥时，FastAPI 冷启动会明确失败。生产环境关闭 `/docs`、`/redoc` 和 `/openapi.json`。

## 3. 初始化 Neon

在本地用直连地址执行：

```bash
source .venv/bin/activate
DATABASE_MIGRATION_URL='postgresql://direct...' python -m backend.database
```

该命令可重复运行，只更新固定路线配置。完成后部署后端并验证：

```bash
curl -fsS https://your-backend.vercel.app/api/v1/health
curl -fsS https://your-backend.vercel.app/api/v1/routes/1
curl -i -X POST https://your-backend.vercel.app/api/v1/weather/refresh
```

最后一个请求应返回 `401`、业务码 `40100` 和 `WWW-Authenticate: Bearer`。

## 4. 创建前端 Project

再次导入同一仓库，Root Directory 设置为 `frontend`，配置：

```dotenv
BACKEND_ORIGIN=https://your-backend.vercel.app
VITE_AMAP_JS_KEY=
```

`vercel.mjs` 在构建时验证 `BACKEND_ORIGIN`，并按顺序生成：

1. `/api/*` 到后端同路径的 rewrite；
2. `/_AMapService/*` 到后端同路径的 rewrite；
3. SPA 的 `/index.html` fallback。

`/assets/` 缓存一年，`/weather/` 缓存 30 天。天气图片已转成 WebP，构建会检查所有引用存在且待上传前端源文件小于 100 MiB。

部署完成后，把前端正式域名加入高德 JS Key 的允许域名。浏览器包中不应出现后端域名、`ADMIN_API_TOKEN` 或 `CRON_SECRET`。

## 5. Cron 与限流

Vercel 每天 UTC 22:00 请求：

```text
GET /api/v1/internal/daily-update
Authorization: Bearer <CRON_SECRET>
```

这对应北京时间 06:00–06:59 的 Hobby 执行窗口，不承诺精确到 06:30。返回约定：

- `200`：成功或当天已执行；
- `207`：部分城市或线路失败；
- `500`：天气和建议均未成功；
- `401`：Cron 凭据缺失或错误。

在后端 Project 配置唯一一条 Hobby 免费 Rate Limit 规则，优先保护 `/_AMapService/*`。初始值可设为每 IP 10 秒 60 次，再依据地图加载日志调整。

## 6. 上线验收

- 首页、地图、天气、剖面、随机旅途和建议 GET 正常。
- 前端浏览器地址保持同源，请求未暴露后端凭据。
- 无令牌管理员 POST 返回 `401`；正确令牌可更新天气和建议。
- Vercel Cron 列表只有计划中的每日任务。
- `daily_update_runs` 当天只有一条记录；重复请求不会再次调用第三方 API。
- Vercel 日志中没有超时、数据库连接耗尽或密钥输出。
- `/docs`、`/redoc`、`/openapi.json` 在生产环境不可用。
- 从中国内地网络分别验证静态资源、API、地图和第三方更新链路。Vercel 没有中国内地计算区域，必须以实测结果为准。

## 7. 恢复与回滚

应用回滚通过 Vercel Deployment 回滚完成。结构变更必须先在独立数据库或 Neon 分支验证；本项目不提供请求期间自动迁移。

数据库恢复使用 Neon 控制台当前套餐提供的恢复能力：

1. 确认控制台显示的实际恢复窗口，不承诺固定 90 天。
2. 从目标时间点创建恢复分支，不直接覆盖生产分支。
3. 用恢复分支运行健康、线路、天气和建议读取检查。
4. 确认数据后按 Neon 指引切换连接或导回生产。
5. 更新 Vercel 环境变量后重新部署并复验。

首次上线必须实际演练一次时间点恢复分支。项目不再配置 ECS、Nginx、systemd、本地 SQLite 备份或阿里云 OSS。
