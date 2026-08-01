# CtoN

重庆至南京高铁沿线的气象可视化演示。天气可从和风天气刷新；配置 DeepSeek 后，页面可依据当前城市观测生成一首短诗。

## 外部 API 配置

从 `.env.example` 复制出未纳入版本控制的 `.env`，再填入实际凭据。前端不会读取这些变量。

```bash
cp .env.example .env
```

DeepSeek 只需要设置 `DEEPSEEK_API_KEY`。`DEEPSEEK_BASE_URL=https://api.deepseek.com` 与 `DEEPSEEK_MODEL=deepseek-v4-flash` 可保留默认值。完成后重启后端，选择城市并点击“生成诗歌”。

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

打开 Vite 显示的本地地址（通常是 `http://localhost:5173`）。前端开发服务器会把 `/api` 请求代理给 `http://localhost:8000`。

## 验证

```bash
source .venv/bin/activate
pytest backend/tests

cd frontend
npm run build
```

运行后端时会自动在 `data/cton.db` 建表并写入固定种子数据。数据库不纳入版本控制；删除该文件后重启服务可重新初始化。
