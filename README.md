# TripCraft Multi-Agent 旅行规划系统

姜兴林的个人项目。使用 LangGraph 编排目的地、航班、酒店、餐饮四个研究 Agent，结合 MCP 工具调用、预算校验、局部重规划和人工确认，生成结构化旅行方案。

## 项目能力

- **Multi-Agent 编排**：四个研究 Agent 并行调研，汇总结果后生成行程，通过共享状态传递数据。
- **工具调用**：LangChain 组织模型和 MCP 工具调用，记录查询来源、查询时间及工具证据，并设置超时与递归上限。
- **约束与重规划**：Pydantic 校验数据结构，Decimal 核算费用；仅预算问题自动重新选择酒店，最多修正两次。
- **人工确认与检查点**：PostgreSQL 保存图检查点，通过 interrupt / Command 确认方案或修改预算后继续执行；SSE 推送节点进度。
- **记忆与缓存**：仅从用户请求抽取长期偏好，按用户和类别原子更新；Redis 查询缓存有效期为 300 秒，缓存异常时继续查询。
- **业务接口**：Next.js 页面支持登录、提交、查看、删除和重试；数据访问范围由服务端会话限定。

## 技术栈

Python 3.12+、LangGraph、LangChain、MCP、FastAPI、Pydantic、SQLAlchemy、PostgreSQL、Redis、SSE、pytest、Next.js、TypeScript、Prisma、Better Auth。

## 先体验演示

演示不需要模型密钥或 PostgreSQL，Redis 可选。安装 uv 后运行：

```powershell
cd backend
uv sync
.\.venv\Scripts\python.exe main.py --demo --port 8060
```

打开 http://127.0.0.1:8060/demo 。默认三天、每人 3000 CNY，固定报价从 4240 元经一次酒店重规划降至 2540 元，确认后完成。将预算改为 1000 元，可以观察修正上限与待处理状态。

**演示使用固定数据并跳过真实模型调用，检查点重启后清空。所有演示报价不可用于预订。**

## 完整项目

1. 在 backend 执行 `uv sync`，复制 `.env.example` 为 `.env` 并填写模型、Exa、PostgreSQL 和可选 Redis 配置。
2. 在 client 执行 `pnpm install`，复制 `.env.example` 为 `.env.local`，连接同一 PostgreSQL 数据库；执行 `pnpm exec prisma generate`、`pnpm exec prisma db push`，并对该库执行 `backend/migrations/create_user_preferences_table.sql`。
3. 本机 Windows 环境可双击根目录的 `start.bat` 启动，双击 `stop.bat` 停止。新机器需按安装位置调整 start.bat 中的 PostgreSQL 路径。后台日志为根目录的 `*.stdout.log`、`*.stderr.log`。

也可以手动运行：

```powershell
# 终端一，在 backend 目录
.\.venv\Scripts\python.exe main.py

# 终端二，在 client 目录
pnpm dev
```

业务页面：http://localhost:3000 。真实查询与人工确认页面：http://127.0.0.1:8000/demo 。原 Next.js 业务页面使用轮询和自动落库，SSE 与人工确认流程通过 /api/planner/* 提供。

真实模式需要可用的模型与外部查询服务；航班查询要求 IATA 机场代码。生成失败会明确报错，业务页面可手动重试，没有模板替代行程。历史检查点可读取并恢复人工确认，但进程崩溃中的任务不会自动重新调度，SSE 事件日志仅保留在当前进程中。

## 代码阅读

- `backend/services/planner.py`：四个研究 Agent、共享状态、条件分支、费用校验与人工确认。
- `backend/tools/travel_mcp.py`：统一的旅行查询 MCP 工具。
- `backend/router/planner.py`：运行、SSE、状态、检查点历史和恢复接口。
- `backend/services/plan_service.py`：原业务入口的结果落库适配。
- `client/lib/trips.ts`：表单校验与提交、重试共用的请求转换。

## 验证

```powershell
# backend 目录
.\.venv\Scripts\python.exe -m pytest tests -q

# client 目录
pnpm test
pnpm exec tsc --noEmit
pnpm lint

# 根目录，先停止本项目服务；此检查会启动和停止前后端
powershell -NoProfile -File tests/start_stop.ps1
```

当前后端 20 项、前端 5 项测试通过。已验证 MCP stdio 调用、预算重规划、人工确认恢复、PostgreSQL 检查点与历史读取、HTTP/SSE 事件和令牌隔离。真实模型分支经过模拟返回测试，并以真实模型结合固定 MCP 报价验证过完整流程；未进行真实市场报价或生产负载评测。

## 开源说明

本项目由姜兴林个人维护和重构。早期旅行示例与部分前端基础参考 awesome-llm-apps；来源和变更说明见 [NOTICE](NOTICE)，许可文本见 [LICENSE](LICENSE)。
