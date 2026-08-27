# CtoN Vercel Hobby 部署手册

本文对应一个个人 Git 仓库、两个 Vercel Project 和一个 Neon PostgreSQL 新加坡数据库。前端与后端全天可访问；定时更新受 Vercel Hobby Cron 调度精度限制。

当前生产状态和已完成验收见 [开发进展与项目状态](Development_Status.md)。本文同时规定首次部署和上线后继续开发的标准流程。

## 当前生产基线

```text
访客入口：https://www.ctonrail.org
Vercel 前端部署域名：https://cton-frontend.vercel.app
后端域名：https://cton-backend.vercel.app
后端 Project Root Directory：仓库根目录
前端 Project Root Directory：frontend
```

公开文档和页面只宣传自定义前端域名。Vercel 前端部署域名和后端域名用于部署、同源 rewrite、健康检查与受保护的运维接口。

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
4. `vercel.json` 将函数区域设为 `sin1`，并为 morning、afternoon、evening 分别注册 `0 23 * * *`、`0 6 * * *`、`0 13 * * *` Cron。FastAPI 默认使用 Fluid Compute，Hobby 的默认最长执行时间为 300 秒。

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

部署完成后，将自定义域名绑定到前端 Project。本项目使用 `www.ctonrail.org` 作为主域名，`ctonrail.org` 通过 `308` 永久跳转到 `www`。外部 DNS 记录保持仅 DNS 解析，不在 Vercel 前增加反向代理。配置后确认两个域名均通过 Vercel 验证，HTTPS 证书包含根域名和 `www` 并启用自动续期。

把自定义正式域名加入高德 JS Key 的允许域名，并保留 Vercel 前端部署域名用于排障。浏览器包中不应出现后端域名、`ADMIN_API_TOKEN` 或 `CRON_SECRET`。

## 5. Cron 与限流

Vercel 每天按三个独立 Cron 请求：

```text
UTC 23:00  GET /api/v1/internal/scheduled-update/morning
UTC 06:00  GET /api/v1/internal/scheduled-update/afternoon
UTC 13:00  GET /api/v1/internal/scheduled-update/evening
Authorization: Bearer <CRON_SECRET>
```

这对应北京时间约 07:00–07:59、14:00–14:59、21:00–21:59 的 Hobby 执行窗口，不承诺精确分钟。三个任务均刷新八城实况、空气质量、大气稳定度和路线建议；morning 额外读取八城当日昼夜预报并逐城回退实况。预计每日约 56 次和风调用、3 次 DeepSeek 调用，建议格式重试时 DeepSeek 最多 6 次。返回约定：

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
- `scheduled_update_runs` 当天最多有三个不同时段记录；同一时段重复请求不会再次调用第三方 API。
- Vercel 日志中没有超时、数据库连接耗尽或密钥输出。
- `/docs`、`/redoc`、`/openapi.json` 在生产环境不可用。
- 从中国内地网络分别验证静态资源、API、地图和第三方更新链路。Vercel 没有中国内地计算区域，必须以实测结果为准。

## 7. 部署后继续开发的标准流程

### 7.1 开始修改前

1. 阅读 `AGENTS.md`、[当前开发状态](Development_Status.md) 和与任务相关的设计文档。
2. 执行 `git status --short`，识别并保留不属于当前任务的修改和未跟踪文件。
3. 确认改动影响前端、后端、数据库结构、环境变量还是多项组合。
4. 云端状态可能变化；涉及发布结论时应读取 Vercel、Neon 或第三方控制台的当前状态，不以文档记录代替实时检查。

### 7.2 本地开发与验证

后端开发使用项目 `.venv`。执行任何会重建数据库的测试前，先确认 PostgreSQL 可连接，且测试库名以 `_test` 结尾：

```bash
pg_isready -h localhost -p 5432
source .venv/bin/activate
TEST_DATABASE_URL='postgresql://localhost/cton_test' pytest -q
pip check
```

严禁把 Neon 生产地址传给 `TEST_DATABASE_URL`。测试套件会清理并重建目标测试库。

前端修改至少运行：

```bash
cd frontend
npm test
BACKEND_ORIGIN=https://cton-backend.vercel.app npm run build
```

依赖变更还应运行适用的安全检查。网络失败的检查必须明确标为未完成，不能报告为通过。

### 7.3 数据库结构变更

当前项目没有通用迁移框架，`python -m backend.database` 主要负责建表和固定数据 UPSERT，不能假设它会自动修改已有表结构。

数据库变更应遵守以下顺序：

1. 在独立本地测试库验证；
2. 在 Neon 分支验证结构变更、初始化和回滚路径；
3. 优先采用向后兼容变更，先更新数据库，再部署后端，最后部署前端；
4. 破坏性字段清理留到所有生产代码不再依赖之后；
5. 执行生产结构变更前再次解析并确认目标是 Neon 直连地址，而不是测试库或池化运行时地址。

### 7.4 提交与自动部署

1. 只暂存当前任务文件，不使用 `git add .` 收集无关内容。
2. 在本地检查通过后提交并推送到 `main`。
3. GitHub 已连接两个 Vercel Project；推送后分别检查 `cton-backend` 和 `cton-frontend` 的部署状态，不能只看到其中一个 Ready 就结束。
4. 环境变量的新增或修改必须发生在依赖它的部署之前；修改 Production 变量后重新部署并复验。
5. 本地 `.vercel/` 和 `.env.local` 只保存 CLI 链接状态，不是生产配置的权威来源，也不得提交。

按改动类型选择发布顺序：

| 改动类型 | 发布顺序 |
|---|---|
| 仅前端且 API 合约不变 | 前端部署 → 页面与同源请求验收 |
| 仅后端且向后兼容 | 后端部署 → API 验收 → 前端回归 |
| 前后端 API 合约同时变化 | 向后兼容后端 → 前端 → 后续清理旧合约 |
| 数据库结构变化 | Neon 分支验证 → 兼容性结构变更 → 后端 → 前端 |
| 环境变量变化 | 先配置变量 → 部署依赖它的 Project → 运行时验收 |

### 7.5 每次发布后的最小验收

所有发布都先检查 Vercel Deployment 为 Ready，再按影响范围执行：

```bash
curl -fsS https://cton-backend.vercel.app/api/v1/health
curl -fsS https://www.ctonrail.org/api/v1/routes/1
curl -fsS https://www.ctonrail.org/api/v1/routes/1/travel-advice
```

此外应确认：

- 首页和一条非首页路径能刷新，SPA fallback 正常；
- 地图、八城路线、天气、剖面和随机旅途无明显回归；
- 浏览器请求保持前端同源，前端产物没有后端安全密钥；
- 后端修改未重新开放生产 `/docs`、`/redoc` 或 `/openapi.json`；
- 写接口无凭据仍返回 `401`；只有涉及第三方更新的改动才使用管理员令牌做真实调用；
- Cron 或更新逻辑变化后，检查一次成功运行和一次同日 `skipped`，并检查日志没有密钥、超时或连接耗尽。

完成发布后更新 [开发进展与项目状态](Development_Status.md)，只写实际验证结果。

## 8. 恢复与回滚

应用回滚通过 Vercel Deployment 回滚完成。结构变更必须先在独立数据库或 Neon 分支验证；本项目不提供请求期间自动迁移。

数据库恢复使用 Neon 控制台当前套餐提供的恢复能力：

1. 确认控制台显示的实际恢复窗口，不承诺固定 90 天。
2. 从目标时间点创建恢复分支，不直接覆盖生产分支。
3. 用恢复分支运行健康、线路、天气和建议读取检查。
4. 确认数据后按 Neon 指引切换连接或导回生产。
5. 更新 Vercel 环境变量后重新部署并复验。

首次上线必须实际演练一次时间点恢复分支。项目不再配置 ECS、Nginx、systemd、本地 SQLite 备份或阿里云 OSS。
