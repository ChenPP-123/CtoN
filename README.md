# CtoN

重庆至南京高铁沿线的气象可视化演示。天气可从和风天气刷新；配置 DeepSeek 后，每次完成沿线天气刷新会自动为成功更新的城市生成一首短诗。

## 外部 API 配置

从 `.env.example` 复制出未纳入版本控制的 `.env`，再填入实际凭据。前端不会读取这些变量。

```bash
cp .env.example .env
```

DeepSeek 只需要设置 `DEEPSEEK_API_KEY`。`DEEPSEEK_BASE_URL=https://api.deepseek.com` 与 `DEEPSEEK_MODEL=deepseek-v4-flash` 可保留默认值。完成后重启后端，点击“更新观测”；天气全部获取完成后，后端会自动为成功城市生成两句或四句的五言、七言绝句。城市切换只读取已保存的诗歌，不会再次调用模型。

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

运行后端时会自动在 `data/cton.db` 建表并写入固定种子数据。数据库不纳入版本控制；删除该文件后重启服务可重新初始化。
