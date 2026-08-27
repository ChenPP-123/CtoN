# CtoN 项目开发约定

## 当前生产基线

- 项目第一版已经上线，访客唯一入口为 `https://www.ctonrail.org`；`cton-frontend.vercel.app` 仅作为 Vercel 底层部署和排障域名保留。
- 同一 GitHub 仓库连接两个 Vercel Project：`cton-backend` 使用仓库根目录，`cton-frontend` 使用 `frontend`。
- 后端运行于 Vercel FastAPI Python 3.13 Function，数据存储在 Neon PostgreSQL；前端通过同源 rewrite 访问后端。
- Vercel Cron 使用 morning、afternoon、evening 三个独立路径，表达式分别为 `0 23 * * *`、`0 6 * * *`、`0 13 * * *`。morning 手动生产运行和同日同时段幂等跳过已经验证；旧 `/api/v1/internal/daily-update` 仅作为过渡兼容入口保留。
- 当前状态、已验证证据和未完成的运维观察统一记录在 `docs/Development_Status.md`；首次部署、持续开发、发布和回滚流程见 `docs/Production_Deployment.md`。

生产状态会变化。新会话涉及部署或线上问题时，先读取上述文档，再用只读检查确认当前 Git、Vercel 和生产接口状态，不把文档中的历史记录当作实时结果。

## 项目文档说明

当前项目中的以下三份文档属于项目初步设计，主要用于说明项目背景、功能方向、数据库思路和接口草案：

- `docs/CtoN_Project_Design_Document.md`
- `docs/CtoN_Database_Design.md`
- `docs/CtoN_API_Interface.md`

这些文档不是不可变的技术规范。在实际开发过程中，应以经过确认的实际需求、当前代码行为、运行环境和验证结果为准。发现文档与实际需要不一致时，应优先实现正确、清晰、可维护的方案，并在必要时同步更新相关文档。

## 开发原则

- 先理解现有代码和数据流，再进行修改。
- 正确性优先，其次是可读性、简单性和可维护性。
- 每个抽象都必须降低整体认知负担；不能降低复杂度的抽象不应引入。
- 保持状态局部化，避免隐藏耦合和不必要的全局状态。
- 优先采用项目已有的框架、目录结构和实现模式。
- 错误应尽早、明确地暴露，并包含足够的排查信息。
- 修改应保持范围明确，避免无关重构和元数据变更。
- 完成修改后运行与变更风险匹配的检查或测试，并说明未执行的验证。

## 本地环境

项目虚拟环境目录为 `.venv`。开发前激活环境：

```bash
source .venv/bin/activate
```

依赖安装、启动命令和测试命令应以项目实际代码和依赖配置为准。

## 新会话起步顺序

1. 执行 `git status --short`，识别用户已有改动，避免覆盖或误提交。
2. 阅读 `docs/Development_Status.md`，确认当前阶段和已知待办。
3. 按任务读取实际代码和对应设计文档；早期设计文档不是高于代码的固定规范。
4. 后端测试前先运行 `pg_isready -h localhost -p 5432`，并确认 `TEST_DATABASE_URL` 的数据库名以 `_test` 结尾。
5. 涉及部署时遵循 `docs/Production_Deployment.md` 的顺序，在每个云端写入、部署、Git 推送或真实第三方调用前取得用户授权。

## 部署后开发边界

- 公开产品始终以一个前端域名为入口；浏览器业务请求使用 `/api/*` 和 `/_AMapService/*` 同源路径，不在前端硬编码后端域名。
- `ADMIN_API_TOKEN`、`CRON_SECRET`、数据库地址和第三方安全密钥只存在于受控环境变量中，不打印、不写入文档、不进入浏览器包。
- Neon 池化 `DATABASE_URL` 供生产运行；非池化直连地址只用于受控初始化或结构维护。严禁用生产库运行测试。
- 数据库结构改动先在本地测试库和 Neon 分支验证。当前没有通用迁移框架，不得假设初始化命令会修改既有表结构。
- 推送后分别验证前端和后端 Vercel Project。配置存在不代表部署或真实第三方链路已经成功。
- 修改生产行为后运行与风险匹配的端到端检查，并把实际结果同步到 `docs/Development_Status.md`。

## 文件和提交约定

- 使用 UTF-8 保存中文文档；代码和配置尽量保持简单、明确。
- 不提交 `.venv`、本地 SQLite 数据库、密钥、缓存和运行日志。
- API Key、数据库连接信息等敏感配置通过环境变量提供。
- 提交前检查工作区变更，避免提交与当前任务无关的文件。
