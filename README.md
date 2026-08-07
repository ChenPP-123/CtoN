# CtoN

重庆至南京高铁沿线的气象可视化演示。天气可从和风天气刷新；城市诗句随天气图片从前端预设中即时选择，配置 DeepSeek 后可根据当天整条线路的观测生成旅途建议。

城市观测台会根据实时风速、云量、观测时间和城市位置，以帕斯奎尔方法估算近地层稳定度。太阳位置在本地计算，不额外调用太阳辐射接口；由于和风天气不提供云底高度和风速观测高度，该结果仅用于教学展示，不用于科研或监管判定。

## 外部 API 配置

从 `.env.example` 复制出未纳入版本控制的 `.env`，再填入实际凭据。前端不会读取这些变量。

```bash
cp .env.example .env
```

DeepSeek 只需要设置 `DEEPSEEK_API_KEY`。`DEEPSEEK_BASE_URL=https://api.deepseek.com` 与 `DEEPSEEK_MODEL=deepseek-v4-flash` 可保留默认值。页面上的“更新观测”会先刷新天气，再调用一次模型生成 50–100 个汉字的全线路建议。模型失败不影响天气数据，并会保留上一次成功建议。城市诗句不调用模型。

## 每日自动更新

后端默认按 `Asia/Shanghai` 时区每天 06:30 自动刷新所有启用线路的天气，天气提交后再为每条线路生成 DeepSeek 建议。后端在当天 06:30 之后启动且当天任务从未执行时会自动补跑；失败会写入 `daily_update_runs` 并保留旧数据，当天不会自动重试，仍可使用页面按钮手动刷新。

```dotenv
APP_TIMEZONE=Asia/Shanghai
DAILY_UPDATE_ENABLED=true
DAILY_UPDATE_TIME=06:30
```

将 `DAILY_UPDATE_ENABLED` 设为 `false` 可关闭定时和启动补跑，不影响手动刷新。时间必须使用 `HH:MM` 格式；配置错误会阻止后端启动，以免任务在错误时间运行。

地图使用高德地图 JavaScript API 2.0。需要设置三个变量：`VITE_AMAP_JS_KEY` 是浏览器加载 SDK 使用的 Key，必须在高德控制台限制为实际前端域名；`AMAP_SECURITY_JS_CODE` 和用于维护固定站点坐标的 `AMAP_WEB_SERVICE_KEY` 只保存在后端 `.env`。安全密钥通过后端的 `/_AMapService/` 同源代理注入，不会进入 Vue 源码。未配置 JS Key 或地图加载失败时，页面会显示可点击的站点列表，天气功能仍可使用。

## 本地运行

终端一：启动后端（首次需要安装依赖）。

```bash
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload
```

终端二：启动前端。

```bash
cd frontend
npm install
npm run dev
```

打开 Vite 显示的本地地址（通常是 `http://localhost:5173`）。前端开发服务器会把 `/api` 和 `/_AMapService` 请求代理给 `http://localhost:8000`。生产环境的反向代理也必须将这两个路径转发到 FastAPI，且将生产域名加入高德 JS Key 的白名单。

## 验证

```bash
source .venv/bin/activate
pytest backend/tests

cd frontend
npm run build
```

运行后端时会自动在 `data/cton.db` 建表并写入固定种子数据。数据库不纳入版本控制；删除该文件后重启服务可重新初始化。生产环境应只启动一个内置调度器；如果多个后端进程共用同一数据库，`daily_update_runs` 的日期唯一键会保证每日任务只有一个进程取得执行权。
